import redis
from comfy_client import ComfyClient

def main():
    r = redis.Redis(host='redis', port=6379)
    client = ComfyClient()

    while True:
        task = r.lpop('tasks')
        if task:
            print(f"Processing task: {task}")
            client.process_task(task)

if __name__ == '__main__':
    main()