# FaaS Scheduler Testbed

  

This repository contains the source code for a Function as a Service (FaaS) framework written in Python, developed as part of a Bachelor's Thesis in Computer Engineering at the University of Pisa. The framework is designed as a **testbed** for the analysis, comparison, and performance evaluation of different scheduling algorithms in a controlled environment.

  

The entire system is containerized using Docker and orchestrated via Docker Compose, ensuring portability and reproducibility of the experiments.

  

>  **Note**: The full thesis that describes the design, implementation, and results in detail is available in this repository: `faas-scheduler-thesis.pdf`

  

## Features

  

*  **Microservices Architecture**: The system consists of a central API Gateway, distributed Execution Nodes, and a test Client, all containerized.

*  **Modular Scheduling Policies**: Thanks to the implementation of the Strategy Pattern, different scheduling algorithms (e.g., `RoundRobin`, `LeastUsed`, `MostUsed`) can be easily implemented and swapped by changing a single line of code.

*  **Support for Various Invocation Strategies**: The framework natively implements `Cold`, `Pre-warmed`, and `Warmed` execution modes to allow for a detailed analysis of the cold start impact.

*  **Automatic Metrics Collection**: Key performance metrics (latency, CPU/RAM usage) are recorded for every invocation into `.csv` and `.txt` files.

*  **Automatic Plot Generation**: A Python script uses the collected data to generate bar charts and box plots, facilitating the visual analysis of the results.

*  **Reproducibility**: The entire environment is defined as code (`docker-compose.yml`) and includes startup scripts that ensure a clean state before each test session.

  

## System Architecture

  

The framework is composed of the following containerized services:

  

*  **API Gateway (`api_gateway`)**: The brain of the system. It is a FastAPI application that exposes a REST API for registering nodes and functions and for orchestrating invocations. It implements the scheduling logic.

*  **Execution Nodes (`ssh_node_1`, ... `ssh_node_4`)**: The workers that execute the functions. They are Ubuntu containers running an SSH server. They receive Docker commands from the gateway to run the function containers.

*  **Client (`client`)**: A Python script that simulates a workload by registering nodes and functions and sending invocation requests to the gateway to start a test session.

*  **Plot Generator (`plot_generator`)**: An on-demand service that analyzes the `metrics.csv` file and generates plots of the results.

  

## Prerequisites

  

To run this project, you need the following installed on your system:

* [Docker Engine](https://docs.docker.com/engine/install/)

* [Docker Compose](https://docs.docker.com/compose/install/)

* [Python 3](https://www.python.org/downloads/) (to run the orchestration scripts)

  

## Quick Start

  

### 1. Clone the Repository

  

```bash

git  clone <https://github.com/TommasoMolesti/faas-scheduler-testbed>

cd  faas-scheduler-testbed

```

  

### 2. Run a Full Test Session

  

The easiest way to start a test session is by using the `start.py` script. This script will:

1. Clean the Docker environment of any leftover containers or images from previous tests.

2. Build the Docker images for all services.

3. Start the entire infrastructure using `docker-compose up`.

4. Run the client, which will send requests to the gateway.

  

To start, simply run:

  

```bash

python3  start.py

```

  

When the execution is finished, you will find the results (metrics files and plots) in the `./results` directory.

  

### 3. Regenerate Plots

  

If you want to regenerate the plots from the existing data without re-running the entire test (e.g., after modifying the `plot_generator/generate.py` script), you can use the command:

  

```bash

python3  generate_plots.py

```

  

### 4. Clean the Results

  

To delete all files in the `./results` directory before a new manual run, use the script:

  

```bash

python3  clean_metrics.py

```

  

## Configuration and Customization

  

The flexibility of this framework allows you to easily customize the experiments by modifying the following files:

  

### Changing Scheduling Policies

  

To change the scheduling policy, open the file `api_gateway/main.py` and modify the following global variables:

  

```python

# Choose the default load-balancing policy

DEFAULT_SCHEDULING_POLICY = policies.RoundRobinPolicy()

# DEFAULT_SCHEDULING_POLICY = policies.LeastUsedPolicy()

# DEFAULT_SCHEDULING_POLICY = policies.MostUsedPolicy()

  

# Choose the high-level node selection strategy

NODE_SELECTION_POLICY = policies.WarmedFirstPolicy()

```

  

### Changing the Warming Strategy

  

To change the container management mode (`Cold`, `Pre-warmed`, `Warmed`), modify the `WARMING_TYPE` variable in `api_gateway/main.py`:

  

```python

# Choose the startup warming mode

WARMING_TYPE = models.EXECUTION_MODES.COLD.value

# WARMING_TYPE = models.EXECUTION_MODES.PRE_WARMED.value

# WARMING_TYPE = models.EXECUTION_MODES.WARMED.value

```

  

### Changing Test Parameters

  

To change the number of invocations, the Docker images used, or the commands executed, open the file `client/constants.py`:

  

```python

# Number of invocation cycles

INVOCATIONS = 100

  

# Docker images for the functions

DOCKER_IMAGE_HEAVY = "tommasomolesti/custom_python_heavy:v8"

DOCKER_IMAGE_LIGHT = "tommasomolesti/custom_python_light:v2"

  

# Commands to simulate different workloads

COMMAND_LIGHT = "python3 loop_function.py 15000"

COMMAND_HEAVY = "python3 loop_function.py 20000"

```

  

## How to Extend the Framework

  

### Adding a New Scheduling Policy

  

To add a new scheduling algorithm, follow these steps:

1. Open the file `api_gateway/policies.py`.

2. Create a new class (e.g., `MyAwesomePolicy`).

3. Implement an asynchronous `select_node` method within the class that respects the same "interface" as the other policies:

```python

async  def  select_node(self, nodes: Dict[str, Any], function_name: str) -> Optional[tuple]:
	# Your selection logic here...

	# ...

	# Return the chosen node's name and a metrics dictionary

	return selected_node, metric_entry

```

4. Import and instantiate your new policy in `api_gateway/main.py`.
  

## Contributing and Contact
This project is open source and I welcome any contributions or suggestions for improvement. If you are a student or researcher interested in FaaS scheduling, feel free to use this framework as a starting point for your own work. I would be happy to see this project extended with new features. For any discussion, questions, or collaboration, you can reach out to me on [LinkedIn](https://www.linkedin.com/in/tommaso-molesti/).
