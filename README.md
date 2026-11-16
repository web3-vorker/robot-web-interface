# RobotViRed backend

Install dependencies and run the API from the project root:

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

The web interface opens at `/`. The API is available at `/api/robot/video`,
`/api/robot/drive`, and `/api/robot/status`. Robot connection settings are read
from `.env`.

## Run with Docker

Create a local environment file, set `ROBOT_HOST` to the robot's LAN address,
then build and run the container from the project root:

```powershell
Copy-Item .env.example .env
docker build -t robotvired .
docker run --rm -p 8000:8000 --env-file .env robotvired
```

Open `http://localhost:8000`. The container listens on port `8000`; robot
connection settings are passed in at runtime and are not baked into the image.
Make sure the computer running Docker can reach the robot over the network.

**Safety:** with `ms=0`, the robot keeps moving until it receives a `stop`
command. Losing the frontend or backend connection does not guarantee that the
robot will stop. The robot's onboard software must implement a watchdog that
stops the motors when commands or heartbeats are missing.
