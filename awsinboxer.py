import os
import sys
import subprocess
import json
import boto3
import botocore
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from colorama import Fore, Style, init
from concurrent.futures import ThreadPoolExecutor
import time
from itertools import cycle
import csv

init(autoreset=True)

CONFIG_FILE = 'aws_ses_config.json'

def install_packages():
    try:
        import boto3
        import colorama
    except ImportError:
        print(Fore.YELLOW + "Installing required packages..." + Style.RESET_ALL)
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'boto3', 'colorama'])
        print(Fore.GREEN + "Packages installed successfully!" + Style.RESET_ALL)

def load_configuration():
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as file:
            return json.load(file)
    return None

def save_configuration(config):
    with open(CONFIG_FILE, 'w') as file:
        json.dump(config, file, indent=4)

def get_aws_quota(client):
    try:
        response = client.get_send_quota()
        return response['Max24HourSend'], response['MaxSendRate'], response['Max24HourSend'] - response['SentLast24Hours']
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'AccessDenied':
            print(Fore.YELLOW + ("Skipping quota check due to insufficient permissions." if lang == "EN" 
                                 else "Passage de la vérification du quota en raison de permissions insuffisantes.") + Style.RESET_ALL)
        else:
            print(Fore.RED + (f"Error retrieving AWS quota: {e}" if lang == "EN" 
                              else f"Erreur lors de la récupération du quota AWS : {e}") + Style.RESET_ALL)
        return None, None, None

def send_raw_email(client, sender_email, recipient, subject, email_content, sender_name):
    try:
        personalized_content = email_content.replace('%name%', recipient['name']).replace('%email%', recipient['email'])
        response = client.send_email(
            Source=f"{sender_name} <{sender_email}>",
            Destination={'ToAddresses': [recipient['email']]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Html': {'Data': personalized_content}}
            }
        )
        print(Fore.GREEN + f"Email sent to {recipient['email']} from {sender_email}" + Style.RESET_ALL)
        return response
    except client.exceptions.ThrottlingException as e:
        print(Fore.RED + f"Throttling error sending to {recipient['email']}: {e}" + Style.RESET_ALL)
        time.sleep(1)
    except Exception as e:
        print(Fore.RED + f"Error sending to {recipient['email']}: {e}" + Style.RESET_ALL)
    return None

def get_aws_credentials():
    access_key_id = input("Enter your AWS Access Key ID: " if lang == "EN" else "Entrez votre AWS Access Key ID : ")
    secret_access_key = input("Enter your AWS Secret Access Key: " if lang == "EN" else "Entrez votre AWS Secret Access Key : ")
    region = input("Enter your AWS region (e.g., us-east-1): " if lang == "EN" else "Entrez votre région AWS (ex: us-east-1) : ")
    sender_file = input("Enter path to verified sender emails file: " if lang == "EN" else "Chemin du fichier des emails vérifiés : ")

    if not os.path.isfile(sender_file):
        print(Fore.RED + ("File not found." if lang == "EN" else "Fichier non trouvé.") + Style.RESET_ALL)
        return None, None, None, None, None

    with open(sender_file, 'r') as f:
        sender_emails = [line.strip() for line in f if line.strip()]

    print(Fore.GREEN + (f"Verified senders loaded: {len(sender_emails)}" if lang == "EN" else f"Expéditeurs vérifiés chargés : {len(sender_emails)}"))
    for email in sender_emails:
        print(Fore.CYAN + f" - {email}")

    sender_name = input("Sender name: " if lang == "EN" else "Nom de l'expéditeur : ")
    return access_key_id, secret_access_key, region, sender_emails, sender_name

def load_recipients(file_path):
    recipients = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            if file_path.lower().endswith('.csv'):
                reader = csv.reader(file)
                for row in reader:
                    if len(row) >= 4:
                        full_name = f"{row[1].strip()} {row[2].strip()}"
                        email = row[3].strip()
                        recipients.append({"email": email, "name": full_name})
            else:
                for line in file:
                    email = line.strip()
                    if email:
                        recipients.append({"email": email, "name": email})
        return recipients
    except Exception as e:
        print(Fore.RED + (f"Error loading recipients: {e}" if lang == "EN"
                          else f"Erreur lors du chargement des destinataires : {e}") + Style.RESET_ALL)
        return []

def load_html_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(Fore.RED + (f"Error loading HTML: {e}" if lang == "EN" else f"Erreur de lecture du HTML : {e}") + Style.RESET_ALL)
        return None

def main():
    global lang
    lang = input("Choose language / Choisissez la langue (EN/FR): ").strip().upper()
    if lang not in ["EN", "FR"]:
        print(Fore.RED + "Invalid choice. Exiting." + Style.RESET_ALL)
        return

    install_packages()

    print(Fore.CYAN + ("=== AWS SES Email Sender ===" if lang == "EN" else "=== Envoi d'e-mails AWS SES ===") + Style.RESET_ALL)
    config = load_configuration()

    if config:
        print(Fore.YELLOW + ("1: Use saved config | 2: New config" if lang == "EN" else "1 : Utiliser config | 2 : Nouvelle config"))
        choice = input("Choice: " if lang == "EN" else "Choix : ").strip()
        if choice == '1':
            aws_access_key_id = config['aws_access_key_id']
            aws_secret_access_key = config['aws_secret_access_key']
            aws_region = config['aws_region']
            sender_emails = config['sender_emails']
            sender_name = config.get('sender_name', "Sender")
        elif choice == '2':
            aws_access_key_id, aws_secret_access_key, aws_region, sender_emails, sender_name = get_aws_credentials()
            if not all([aws_access_key_id, aws_secret_access_key, aws_region, sender_emails]):
                return
            save_configuration({
                'aws_access_key_id': aws_access_key_id,
                'aws_secret_access_key': aws_secret_access_key,
                'aws_region': aws_region,
                'sender_emails': sender_emails,
                'sender_name': sender_name
            })
        else:
            print(Fore.RED + "Invalid choice." + Style.RESET_ALL)
            return
    else:
        aws_access_key_id, aws_secret_access_key, aws_region, sender_emails, sender_name = get_aws_credentials()
        if not all([aws_access_key_id, aws_secret_access_key, aws_region, sender_emails]):
            return
        save_configuration({
            'aws_access_key_id': aws_access_key_id,
            'aws_secret_access_key': aws_secret_access_key,
            'aws_region': aws_region,
            'sender_emails': sender_emails,
            'sender_name': sender_name
        })

    try:
        client = boto3.client('ses', region_name=aws_region,
                              aws_access_key_id=aws_access_key_id,
                              aws_secret_access_key=aws_secret_access_key)
        print(Fore.GREEN + "SES client created." + Style.RESET_ALL)
    except Exception as e:
        print(Fore.RED + f"Failed to create SES client: {e}" + Style.RESET_ALL)
        return

    recipients_file = input("Path to recipients (.txt or .csv): ")
    if not os.path.isfile(recipients_file):
        print(Fore.RED + "File not found." + Style.RESET_ALL)
        return

    recipients = load_recipients(recipients_file)
    if not recipients:
        print(Fore.RED + "No recipients." + Style.RESET_ALL)
        return

    print(Fore.YELLOW + f"Loaded {len(recipients)} recipients." + Style.RESET_ALL)

    quota = get_aws_quota(client)
    if quota[0] is not None:
        print(Fore.CYAN + f"Quota: {quota[2]} remaining / {quota[0]} | Rate: {quota[1]}/s" + Style.RESET_ALL)

    confirm = input("Send emails now? (Y/N): " if lang == "EN" else "Envoyer maintenant ? (Y/N) : ").strip().lower()
    if confirm != 'y':
        print(Fore.RED + "Cancelled." + Style.RESET_ALL)
        return

    html_path = input("HTML file path: ")
    email_content = load_html_file(html_path)
    if not email_content:
        return

    subject = input("Subject: ")
    try:
        rate = int(input("Emails per second (max 14): "))
        rate = min(rate, 14)
    except ValueError:
        print(Fore.RED + "Invalid rate." + Style.RESET_ALL)
        return

    sender_cycle = cycle(sender_emails)

    def send_task(recipient):
        sender = next(sender_cycle)
        send_raw_email(client, sender, recipient, subject, email_content, sender_name)

    print(Fore.CYAN + "Sending..." + Style.RESET_ALL)
    with ThreadPoolExecutor(max_workers=rate) as executor:
        for recipient in recipients:
            executor.submit(send_task, recipient)
            time.sleep(1.0 / rate)

    print(Fore.GREEN + ("Finished sending." if lang == "EN" else "Envois terminés.") + Style.RESET_ALL)

if __name__ == '__main__':
    main()
