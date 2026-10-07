"""Train the utterance-level accent model (app/accent/model.py).

Data come from tools/build_cache.py caches (and tools/repitch.py caches):
  exact / label / repitch phrases   trusted labels
  engine phrases                    only through pseudo-labels: the current
                                    model's posterior times a prior from the
                                    engine's expected accent (and, for JVS
                                    parallel100, what most speakers said);
                                    kept when ≥ PSEUDO_P sure (--pseudo)

The loss is a partial-label cross-entropy: −log of the probability of all
classes the label allows, after merging classes the audio can't tell apart.
Each batch drops its highest-loss non-exact phrases (likely native variants
or label errors).

Usage (from backend/):
  ../.venv/bin/python -m tools.train_accent CACHE.pkl [...] [--pseudo] [--epochs 20] [--save]
      [--ssl PCA.npz]
"""

from __future__ import annotations

import argparse
import pickle
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from app.accent.detect import MIN_VOICED, class_groups
from app.accent.model import MODEL, N_FEATURES, _torch_model, batch_index, phrase_classes, utterance_features
from app.audio.ssl import LAYERS

from .add_f0 import use_f0
from .evaluate import reliable_moras
from .ssl_feats import attach, load_pca

TRUSTED = {"exact", "label", "repitch", "user"}
PSEUDO_P = 0.9
DROP_FRAC = 0.07
USE_SSL = False  # --ssl: add the speech-model features (rec["ssl"], tools/ssl_feats.py)


def features(rec):
    x, voiced = utterance_features(rec)
    if USE_SSL:
        x = np.concatenate([x, np.asarray(rec["ssl"], dtype=np.float32)], axis=1)
    return x, voiced


def norm_labels(labels: list[int], n: int) -> set[int]:
    s = set(labels)
    if 0 in s or n in s:
        s |= {0, n}
    return s


def target_mask(rec, ph, labels, voiced) -> np.ndarray | None:
    """Classes the label allows, widened to every class the audio can't
    tell apart from them. None when there is nothing to learn."""
    n = ph["e"] - ph["s"]
    classes, _ = phrase_classes(n, rec["special"][ph["s"]:ph["e"]])
    obs = (voiced[ph["s"]:ph["e"]] >= MIN_VOICED) & np.asarray(reliable_moras(rec, ph), dtype=bool)
    if obs.sum() < 2:
        return None
    labels = norm_labels(labels, n)
    groups = class_groups(classes, n, obs)
    ok_groups = {g for g, c in zip(groups, classes) if set(c) & labels}
    mask = np.array([g in ok_groups for g in groups])
    if mask.all() or not mask.any():
        return None
    return mask


def prepare(recs, pseudo_labels=None):
    """[(features, phrase items, masks, kinds)] per utterance."""
    data = []
    for r in recs:
        if USE_SSL and "ssl" not in r:
            continue
        x, voiced = features(r)
        items, masks, kinds = [], [], []
        for k, ph in enumerate(r["phrases"]):
            if ph["e"] - ph["s"] < 2:
                continue
            labels = None
            if ph["kind"] in TRUSTED:
                labels = ph["labels"]
            elif pseudo_labels is not None:
                labels = pseudo_labels.get((r["utt"], k))
            if labels is None:
                continue
            m = target_mask(r, ph, labels, voiced)
            if m is None:
                continue
            items.append((ph["s"], ph["e"], list(r["special"][ph["s"]:ph["e"]])))
            masks.append(m)
            kinds.append(ph["kind"])
        if items:
            data.append((x, items, masks, kinds, r["spk"]))
    return data


def collate(batch, device):
    xs = [torch.from_numpy(b[0]) for b in batch]
    lengths = torch.tensor([len(x) for x in xs])
    x = torch.nn.utils.rnn.pad_sequence(xs, batch_first=True).to(device)
    items, masks, kinds = [], [], []
    for bi, (_, its, ms, ks, _) in enumerate(batch):
        for (s, e, sp), m, k in zip(its, ms, ks):
            items.append((bi, s, e, sp))
            masks.append(m)
            kinds.append(k)
    idx = {k: (v.to(device) if torch.is_tensor(v) else v) for k, v in batch_index(items).items()}
    width = idx["shape"][1]
    mask = torch.zeros(len(masks), width, dtype=torch.bool)
    for i, m in enumerate(masks):
        mask[i, :len(m)] = torch.from_numpy(m)
    return x, lengths, idx, mask.to(device), kinds


def phrase_losses(logits, mask):
    logp = torch.log_softmax(logits, dim=-1)
    return -torch.logsumexp(logp.masked_fill(~mask, float("-inf")), dim=-1)


def run_epoch(net, data, opt, device, train=True, bs=32):
    net.train(train)
    order = list(range(len(data)))
    if train:
        random.shuffle(order)
    total, count, hits = 0.0, 0, 0
    for i in range(0, len(order), bs):
        batch = [data[j] for j in order[i:i + bs]]
        x, lengths, idx, mask, kinds = collate(batch, device)
        with torch.set_grad_enabled(train):
            logits = net(x, lengths, idx)
            loss = phrase_losses(logits, mask)
            if train:
                keep = torch.ones_like(loss, dtype=torch.bool)
                soft = torch.tensor([k not in ("exact", "repitch") for k in kinds], device=device)
                if soft.sum() > 10:
                    cut = torch.quantile(loss[soft].detach(), 1 - DROP_FRAC)
                    keep &= ~(soft & (loss > cut))
                opt.zero_grad()
                loss[keep].mean().backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
                opt.step()
        total += float(loss.detach().sum())
        count += len(loss)
        hits += int(mask.gather(1, logits.argmax(-1, keepdim=True)).sum())
    return total / max(count, 1), hits / max(count, 1)


def fit_temperature(net, data, device) -> float:
    net.eval()
    all_logits, all_masks = [], []
    with torch.no_grad():
        for i in range(0, len(data), 64):
            x, lengths, idx, mask, _ = collate(data[i:i + 64], device)
            all_logits.append(net(x, lengths, idx).cpu())
            all_masks.append(mask.cpu())
    best, best_t = None, 1.0
    for t in np.arange(0.5, 3.01, 0.1):
        nll = sum(float(phrase_losses(lg / t, m).sum()) for lg, m in zip(all_logits, all_masks))
        if best is None or nll < best:
            best, best_t = nll, float(t)
    return best_t


def pseudo_label(recs, net_temp) -> dict:
    """(utt, phrase index) → accepted accents, from model posterior × prior."""
    from app.accent import model as M

    net, temp = net_temp
    M.load.cache_clear()
    # what most parallel100 speakers said, per (sentence, phrase index)
    votes: dict = defaultdict(Counter)
    posts = {}
    for r in recs:
        if any(ph["kind"] == "engine" for ph in r["phrases"]):
            dets = _detect(net, temp, r)
            posts[r["utt"]] = dets
            if r.get("part") == "parallel100":
                sent = r["utt"].split("/")[1]
                for k, d in enumerate(dets):
                    if d is not None and max(d[1]) >= PSEUDO_P:
                        votes[(sent, k, len(r["phrases"]))][d[0][int(np.argmax(d[1]))][0]] += 1
    out = {}
    for r in recs:
        dets = posts.get(r["utt"])
        if dets is None:
            continue
        sent = r["utt"].split("/")[1]
        for k, (ph, d) in enumerate(zip(r["phrases"], dets)):
            if ph["kind"] != "engine" or d is None or ph["conf"] == "uncertain":
                continue
            n = ph["e"] - ph["s"]
            exp = norm_labels(ph["labels"], n)
            vote = votes.get((sent, k, len(r["phrases"])))
            major = vote.most_common(1)[0][0] if vote and sum(vote.values()) >= 10 else None
            classes, post = d
            prior = np.array([0.7 if set(c) & exp else 0.3 / max(len(classes) - 1, 1) for c in classes])
            if major is not None:
                prior *= np.array([2.0 if major in c else 1.0 for c in classes])
            p = np.asarray(post) * prior
            p /= p.sum()
            j = int(np.argmax(p))
            if p[j] >= PSEUDO_P:
                out[(r["utt"], k)] = classes[j]
    return out


def _detect(net, temp, rec):
    if USE_SSL and "ssl" not in rec:
        return [None] * len(rec["phrases"])
    x, _ = features(rec)
    items, ks = [], []
    for k, ph in enumerate(rec["phrases"]):
        if ph["e"] - ph["s"] >= 2:
            items.append((0, ph["s"], ph["e"], list(rec["special"][ph["s"]:ph["e"]])))
            ks.append(k)
    out = [None] * len(rec["phrases"])
    if not items:
        return out
    with torch.no_grad():
        p = torch.softmax(net(torch.from_numpy(x)[None], torch.tensor([len(x)]), batch_index(items)) / temp,
                          -1).numpy()
    for (_, s, e, sp), k, pr in zip(items, ks, p):
        classes, _ = phrase_classes(e - s, sp)
        out[k] = (classes, [float(pr[c]) for c in range(len(classes))])
    return out


def train(train_data, dev_data, epochs, device, hidden=64, config=None):
    net = _torch_model()(**(config or {"d_in": N_FEATURES, "h": hidden})).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    best, best_state = None, None
    for ep in range(epochs):
        tl, ta = run_epoch(net, train_data, opt, device)
        dl, da = run_epoch(net, dev_data, opt, device, train=False)
        sched.step()
        print(f"epoch {ep:2d}  train loss {tl:.3f} acc {ta:.3f}   dev loss {dl:.3f} acc {da:.3f}", flush=True)
        if best is None or dl < best:
            best, best_state = dl, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)
    return net


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caches", type=Path, nargs="+")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--hidden", type=int, default=64)
    ap.add_argument("--pseudo", type=int, default=0, help="self-training rounds on engine-labelled data")
    ap.add_argument("--save", action="store_true", help="write app/accent/accent_model.pt")
    ap.add_argument("--out", type=Path, help="write the checkpoint here instead")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--f0", default="praat", help="pitch track to read (tools/add_f0.py)")
    ap.add_argument("--ssl", type=Path, help="PCA basis (tools/ssl_feats.py): also use speech-model features")
    ap.add_argument("--ssl-drop", type=float, default=0.3, help="share of utterances trained without them")
    args = ap.parse_args()
    global USE_SSL
    USE_SSL = bool(args.ssl)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    recs = []
    for p in args.caches:
        part = pickle.loads(p.read_bytes())
        if args.ssl:
            attach(part, p)
        recs += part
    use_f0(recs, args.f0)
    config = {"d_in": N_FEATURES, "h": args.hidden}
    pca = None
    if args.ssl:
        pca = load_pca(args.ssl)
        config.update(d_ssl=len(LAYERS) * pca["comp"].shape[2], n_layers=len(LAYERS), ssl_drop=args.ssl_drop)
    train_recs = [r for r in recs if r["split"] == "train"]
    dev_recs = [r for r in recs if r["split"] == "dev"]
    print(f"{len(train_recs)} train / {len(dev_recs)} dev utterances")
    train_data, dev_data = prepare(train_recs), prepare(dev_recs)
    print(f"{sum(len(d[1]) for d in train_data)} train phrases with trusted labels")
    net = train(train_data, dev_data, args.epochs, device, args.hidden, config)
    temp = fit_temperature(net, dev_data, device)

    for rnd in range(args.pseudo):
        net.cpu()
        pl = pseudo_label(train_recs, (net, temp))
        print(f"round {rnd + 1}: {len(pl)} pseudo-labelled phrases")
        train_data = prepare(train_recs, pl)
        net = train(train_data, dev_data, args.epochs, device, args.hidden, config)
        temp = fit_temperature(net, dev_data, device)

    print(f"temperature {temp:.2f}")
    if args.save or args.out:
        torch.save({"config": config, "state": net.cpu().state_dict(),
                    "temperature": temp, "f0": args.f0, "ssl_pca": pca,
                    "data": sorted({f"{r['src']}/{r.get('part', '')}" for r in train_recs})},
                   args.out or MODEL)
        print("saved", args.out or MODEL)


if __name__ == "__main__":
    main()
