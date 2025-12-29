document.getElementById('prompt-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const prompt = document.getElementById('prompt').value;
    document.getElementById('progress').innerText = '處理中...';

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt }),
        });

        if (response.ok) {
            const result = await response.json();
            document.getElementById('progress').innerText = '完成: ' + result.status;
        } else {
            document.getElementById('progress').innerText = '錯誤: ' + response.statusText;
        }
    } catch (error) {
        document.getElementById('progress').innerText = '發生錯誤: ' + error.message;
    }
});