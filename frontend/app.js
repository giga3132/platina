text_input = document.getElementById('text-form');


text_input.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = document.getElementById('text-input').value;
    const response = await fetch('http://localhost:5000/text-to-pitch', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ text })
    });
    const data = await response.json();
    document.getElementById('result').innerText = data.pitch;
});