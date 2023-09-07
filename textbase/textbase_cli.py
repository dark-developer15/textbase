import inspect
import click
import requests
import subprocess
import os
from tabulate import tabulate
from time import sleep
from yaspin import yaspin
import importlib.resources
import re
import zipfile


CLOUD_URL = "https://us-east1-chat-agents.cloudfunctions.net/deploy-from-cli"
UPLOAD_URL = "https://us-east1-chat-agents.cloudfunctions.net/upload-file"

@click.group()
def cli():
    pass

@cli.command()
@click.option("--path", prompt="Path to the main.py file", required=True)
@click.option("--port", prompt="Enter port", required=False, default=8080)
def test(path, port):
    # Check if the file exists
    if not os.path.exists(path):
        click.secho("Incorrect main.py path.", fg='red')
        return

    # Load the module dynamically
    spec = importlib.util.spec_from_file_location("module.name", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Check if 'on_message' exists and is a function
    if "on_message" in dir(module) and inspect.isfunction(getattr(module, "on_message")):
        click.secho("The function 'on_message' exists in the specified main.py file.", fg='yellow')
    else:
        click.secho("The function 'on_message' does not exist in the specified main.py file.", fg='red')
        return
    server_path = importlib.resources.files('textbase').joinpath('utils', 'server.py')
    try:
        if os.name == 'posix':
            process_local_ui = subprocess.Popen(f'python3 {server_path}', shell=True)
        else:
            process_local_ui = subprocess.Popen(f'python {server_path}', shell=True)

        process_gcp = subprocess.Popen(f'functions_framework --target=on_message --source={path} --debug --port={port}',
                     shell=True,
                     stdin=subprocess.PIPE)
        
        # Print the Bot UI Url
        encoded_api_url = urllib.parse.quote(f"http://localhost:{port}", safe='')
        click.secho(f"Server URL: http://localhost:4000/?API_URL={encoded_api_url}", fg='cyan', bold=True)
        process_local_ui.communicate()
        process_gcp.communicate()  # Wait for the process to finish
    except KeyboardInterrupt:
        process_gcp.kill()  # Stop the process when Ctrl+C is pressed
        process_local_ui.kill()
        click.secho("Server stopped.", fg='red')

#################################################################################################################
def fileExist(path):
    if not os.path.exists(os.path.join(path, "main.py")):
        click.echo(click.style(f"Error: main.py not found in {path} directory.", fg='red'))
        return False
    if not os.path.exists(os.path.join(path, "requirements.txt")):
        click.echo(click.style(f"Error: requirements.txt not found in {path} directory.", fg='red'))
        return False
    return True
    
@cli.command()
@click.option("--path", prompt="Path to the directory containing main.py and requirements.txt file", required=True)
def compress(path):
    click.echo(click.style(f"Creating zip file for deployment", fg='green'))
    output_zip_filename = 'deploy.zip'
    if fileExist(path):
        with zipfile.ZipFile(output_zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(path):
                for file in files:
                    if file != output_zip_filename:    
                        file_path = os.path.join(root, file)
                        # Add the file to the zip archive
                        zipf.write(file_path, os.path.relpath(file_path, path))
        click.echo(click.style(f"Files have been zipped to {output_zip_filename}", fg='green'))

#################################################################################################################
def validate_bot_name(ctx, param, value):
    pattern = r'^[a-z0-9_-]+$'
    if not re.match(pattern, value):
        error_message = click.style('Bot name can only contain lowercase alphanumeric characters, hyphens, and underscores.', fg='red')
        raise click.BadParameter(error_message)
    return value


@cli.command()
@click.option("--path", prompt="Path to the zip folder", required=True)
@click.option("--bot_name", prompt="Name of the bot", required=True, callback=validate_bot_name)
@click.option("--api_key", prompt="Textbase API Key", required=True)
def deploy(path, bot_name, api_key):
    click.echo(click.style(f"Deploying bot '{bot_name}' with zip folder from path: {path}", fg='yellow'))

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    files = {
        "file": open(path, "rb"),
    }

    data = {
        "botName": bot_name
    }

    with yaspin(text="Uploading...", color="yellow") as spinner:
        response = requests.post(
            UPLOAD_URL,
            headers=headers,
            data=data,
            files=files
        )

    if response.ok:
        click.echo(click.style("Upload completed successfully! ✅", fg='green'))
        response_data = response.json()
        error = response_data.get('error')
        data = response_data.get('data')
        if not error and data:
            message = data.get('message')
            # Parse the message to extract bot ID and URL
            parts = message.split('. ')
            bot_id = parts[1].split(' ')[-1]
            url = parts[2].split(' ')[-1]
            # Create a list of dictionaries for tabulate
            data_list = [{'Status': parts[0], 'Bot ID': bot_id, 'URL': url}]
            table = tabulate(data_list, headers="keys", tablefmt="pretty")
            click.echo(click.style("Deployment details:", fg='blue'))
            click.echo(table)
        else:
            click.echo(click.style("Something went wrong! ❌", fg='red'))
            click.echo(response.text)
    else:
        click.echo(click.style("Something went wrong! ❌", fg='red'))
        click.echo(response.text)
#################################################################################################################

@cli.command()
@click.option("--bot_id", prompt="Id of the bot", required=True)
@click.option("--api_key", prompt="Textbase API Key", required=True)
def health(bot_id, api_key):
    click.echo(click.style(f"Checking health of bot '{bot_id}' with API key: {api_key}", fg='green'))

    # the user would get the bot_id from the GET /list and use it here
    cloud_url = f"{CLOUD_URL}/bot-health"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    params = {
        "botId": bot_id
    }

    response = requests.get(cloud_url, headers=headers, params=params)

    if response.ok:
        response_data = response.json()
        data = response_data.get('data')
        if data is not None:
            # Convert the data dictionary to a list of dictionaries for tabulate
            data_list = [data]
            table = tabulate(data_list, headers="keys", tablefmt="pretty")
            click.echo(click.style("Bot status:", fg='green'))
            click.echo(table)
        else:
            click.echo(click.style("Status information not found in the response.", fg='red'))
            click.echo(response_data)
    else:
        click.echo(click.style("Failed to retrieve bot status.", fg='red'))


@cli.command()
@click.option("--api_key", prompt="Textbase API Key", required=True)
def list(api_key):
    click.echo(click.style("Getting the list of bots...", fg='green'))

    cloud_url = f"{CLOUD_URL}/list"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    response = requests.get(
        cloud_url,
        headers=headers
    )

    if response.ok:
        data = response.json().get('data', [])
        if data:
            # Reorder the dictionaries in the data list
            reordered_data = [{'id': d['id'], 'name': d['name'], 'url': d['url']} for d in data]
            table = tabulate(reordered_data, headers="keys", tablefmt="pretty")
            click.echo(click.style("List of bots:", fg='blue'))
            print(table)
        else:
            click.echo(click.style("No bots found.", fg='yellow'))
    else:
        click.echo(click.style("Something went wrong!", fg='red'))


@cli.command()
@click.option("--bot_id", prompt="Id of the bot", required=True)
@click.option("--api_key", prompt="Textbase API Key", required=True)
def delete(bot_id, api_key):
    click.echo(click.style(f"Deleting bot '{bot_id}'...", fg='red'))

    cloud_url = f"{CLOUD_URL}/delete"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    data = {
        "botId": bot_id
    }

    with click.progressbar(length=100, label='Deleting...') as bar:
        for i in range(100):
            sleep(0.02)  # simulate deletion progress
            bar.update(1)

    response = requests.post(
        cloud_url,
        json=data,
        headers=headers
    )

    if response.ok:
        click.echo(click.style(f"Bot '{bot_id}' deleted successfully!", fg='green'))
        response_data = response.json()
        if response_data:
            # Convert the data dictionary to a list of dictionaries for tabulate
            data_list = [response_data]
            table = tabulate(data_list, headers="keys", tablefmt="pretty")
            click.echo(table)
        else:
            click.echo("No data found in the response.")
    else:
        click.echo(click.style("Something went wrong!", fg='red'))

if __name__ == "__main__":
    cli()

