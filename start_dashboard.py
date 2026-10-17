"""Start the primary React/Flask dashboard; Streamlit is explicit rollback only."""

import argparse
from getpass import getpass
import os
import re
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv


def validate_environment(env, independent_api=False):
    required = ["DASHBOARD_ADMIN_USERNAME", "DASHBOARD_ADMIN_PASSWORD_HASH",
                "CLOUD_DB_HOST", "CLOUD_DB_USER", "CLOUD_DB_PASSWORD", "CLOUD_DB_NAME"]
    if not independent_api:
        required += ['FLASK_APP_URL', 'DASHBOARD_API_TOKEN']
    missing = [name for name in required if not env.get(name, "").strip()]
    if missing:
        raise ValueError("Missing dashboard settings: " + ", ".join(missing))
    if env.get("USE_CLOUD_DB", "").lower() != "true":
        raise ValueError("Hosted dashboard requires USE_CLOUD_DB=true.")
    password_hash = env["DASHBOARD_ADMIN_PASSWORD_HASH"]
    if not re.fullmatch(r"[a-fA-F0-9]{64}", password_hash):
        raise ValueError("DASHBOARD_ADMIN_PASSWORD_HASH must be a SHA-256 hash.")
    from auth_helpers import hash_password
    if password_hash.lower() in {hash_password("admin123"), hash_password("admin1234")}:
        raise ValueError("Set a dashboard password other than the development default.")
    if not independent_api and not env["FLASK_APP_URL"].startswith("https://"):
        raise ValueError("FLASK_APP_URL must use HTTPS for the hosted chatbot.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-streamlit', action='store_true', help='Run the retained Streamlit rollback dashboard instead.')
    parser.add_argument('--read-only', action='store_true', help='Disable school-data changes during React dashboard validation.')
    parser.add_argument('--local-setup', action='store_true', help='Choose private, session-only login credentials and open the existing cloud data locally with editing enabled.')
    args = parser.parse_args(argv)
    if args.read_only and args.legacy_streamlit:
        parser.error('--read-only is supported only by the primary React dashboard.')
    load_dotenv()
    if args.local_setup:
        if args.legacy_streamlit or os.getenv('DASHBOARD_HOSTED') == 'true' or os.getenv('RENDER') == 'true':
            parser.error('--local-setup is only available for the local primary dashboard.')
        if os.getenv('USE_CLOUD_DB', '').lower() != 'true':
            sys.exit('Local school-data setup requires the existing USE_CLOUD_DB=true configuration.')
        from auth_helpers import hash_password
        from validators import validate_username
        print('YaraBot primary dashboard: existing school database, not sample data.')
        print('Saved changes affect the chatbot. Credentials stay in this process only.')
        while True:
            username = input('Choose your dashboard username: ').strip()
            valid, message = validate_username(username)
            if valid and len(username) <= 100:
                break
            print(message or 'Use a username of at most 100 characters.')
        while True:
            password = getpass('Choose a private password (12+ characters, hidden): ')
            if not 12 <= len(password) <= 512 or password in {'synthetic-password', 'test-dashboard-password'}:
                print('Use a private password of 12 to 512 characters, not a sample password.')
                continue
            if password != getpass('Confirm password (hidden): '):
                print('Passwords did not match. Try again.')
                continue
            break
        os.environ.update(DASHBOARD_ADMIN_USERNAME=username,
                          DASHBOARD_ADMIN_PASSWORD_HASH=hash_password(password),
                          DASHBOARD_SESSION_SECRET=secrets.token_urlsafe(48),
                          DASHBOARD_READ_ONLY='true' if args.read_only else 'false',
                          DASHBOARD_LIVE_DATA='true', PORT='5010')
        del password
    if args.read_only:
        os.environ['DASHBOARD_READ_ONLY'] = 'true'
    if args.legacy_streamlit:
        try:
            validate_environment(os.environ)
        except ValueError as error:
            sys.exit(str(error))
        os.environ["DASHBOARD_HOSTED"] = "true"
        script = str(Path(__file__).with_name("dashboard.py"))
        os.execv(sys.executable, [sys.executable, "-m", "streamlit", "run", script,
                                 "--server.address=0.0.0.0", f"--server.port={os.getenv('PORT', '8501')}",
                                 "--server.headless=true", "--browser.gatherUsageStats=false"])
        return
    if os.getenv('DASHBOARD_HOSTED') == 'true' or os.getenv('RENDER') == 'true':
        os.execv(sys.executable, [sys.executable, '-m', 'gunicorn', 'admin_app:create_app()',
                                 '--bind', f"0.0.0.0:{os.getenv('PORT', '10000')}",
                                 '--workers', '1', '--threads', '2', '--timeout', '240', '--access-logfile', '-'])
        return
    from admin_app import create_app, DIST
    if not DIST.joinpath('index.html').is_file():
        sys.exit('Build the dashboard first: cd admin_frontend, then npm ci and npm run build.')
    try:
        app = create_app()
    except (ValueError, RuntimeError) as error:
        sys.exit(str(error))
    print('Open http://127.0.0.1:' + os.getenv('PORT', '5010') + ' and sign in with the credentials you chose.')
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5010')), debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
