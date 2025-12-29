from flask import Flask, request, jsonify
from redis import Redis

app = Flask(__name__)
redis = Redis(host='redis', port=6379)

@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    prompt = data.get('prompt')
    # Push task to Redis
    redis.rpush('tasks', prompt)
    return jsonify({'status': 'Task received'}), 200

@app.route('/status/<task_id>', methods=['GET'])
def status(task_id):
    # Placeholder for task status
    return jsonify({'status': 'In progress'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)