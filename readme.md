# Documentation

This script provides instructions for setting up and running a Dockerized Python application for downloading lessons. Below is a breakdown of the commands and their purposes:

1. **Build the Docker Image**:
    - `docker-compose build`: Builds the Docker image for the application.

2. **Run the Application**:
    - `docker-compose run --rm rocket_download`: Runs the application in a one-off container and removes the container after execution.

3. **Start the Application in Detached Mode**:
    - `docker-compose up -d --build`: Starts the application in detached mode, rebuilding the image if necessary.

4. **Access the Running Container**:
    - `docker compose exec rocket_download bash`: Opens a bash shell inside the running container for debugging or manual execution.

5. **Run the Python Script**:
    - `python main.py`: Executes the main Python script inside the container.

6. **Local Development Setup**:
    - `RUN pip install --no-cache-dir -r requirements.txt`: Installs the required Python dependencies locally without caching.
    - `python main.py`: Runs the Python script locally after setting up the environment.
    7. **Run Locally**:
        - To run the application locally without Docker, ensure all dependencies are installed using:
            - `pip install --no-cache-dir -r requirements.txt`
        - Then execute the script:
            - `python main.py`

    8. **Set Up Virtual Environment**:
        - To isolate dependencies, create and activate a virtual environment:
            - On Unix/macOS:
                - `python3 -m venv venv`
                - `source venv/bin/activate`
            - On Windows:
                - `python -m venv venv`
                - `venv\Scripts\activate`
        - Install dependencies within the virtual environment:
            - `pip install --no-cache-dir -r requirements.txt`
        - Run the script:
            - `python main.py`