import utils

if __name__ == "__main__":
    utils.run_command("docker-compose run --rm --build plot_generator", stream_output=True)