#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone Dahua connection tester (no Odoo required).

Use this to verify connectivity, login, serial number and attendance fetching
against your device *before* configuring it in Odoo - it uses the exact same
client code the module uses.

Examples
--------
# Private protocol (SmartPSS default), port 37777:
python3 test_connection.py --host 192.168.1.108 --user admin --password Abcd1234 --debug

# HTTP RPC transport instead:
python3 test_connection.py --host 192.168.1.108 --mode http --port 80 \
        --user admin --password Abcd1234 --debug

# Fetch the last 48h of attendance records:
python3 test_connection.py --host 192.168.1.108 --user admin --password Abcd1234 --hours 48

# Push (enroll) a user onto the device, optionally with a card:
python3 test_connection.py --host 192.168.1.108 --user admin --password Abcd1234 \
        --push-user 1001 --push-name "John Doe" --push-card 0012345678

# Query / remove a user on the device:
python3 test_connection.py --host 192.168.1.108 --user admin --password Abcd1234 --get-user 1001
python3 test_connection.py --host 192.168.1.108 --user admin --password Abcd1234 --remove-user 1001
"""
import argparse
import os
import sys
import time

# Allow running from anywhere: add the parent module dir so we can import the client.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models'))

from dahua_rpc_client import DahuaRpcClient, DahuaRpcError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='Dahua connection tester')
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=None,
                        help='Defaults to 37777 for dhip, 80 for http.')
    parser.add_argument('--mode', choices=['dhip', 'http'], default='dhip')
    parser.add_argument('--user', default='admin')
    parser.add_argument('--password', default='')
    parser.add_argument('--ssl', action='store_true')
    parser.add_argument('--hours', type=int, default=24,
                        help='How many hours of past records to fetch.')
    parser.add_argument('--push-user', dest='push_user',
                        help='Enroll/push this User ID onto the device.')
    parser.add_argument('--push-name', dest='push_name', default=None,
                        help='Name to use with --push-user.')
    parser.add_argument('--push-card', dest='push_card', default=None,
                        help='Optional card number to attach with --push-user.')
    parser.add_argument('--get-user', dest='get_user',
                        help='Query this User ID on the device.')
    parser.add_argument('--remove-user', dest='remove_user',
                        help='Delete this User ID from the device.')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    port = args.port or (37777 if args.mode == 'dhip' else (443 if args.ssl else 80))

    print('Connecting to %s:%s (mode=%s, ssl=%s) ...' % (args.host, port, args.mode, args.ssl))
    client = DahuaRpcClient(host=args.host, port=port, username=args.user,
                            password=args.password, mode=args.mode,
                            use_ssl=args.ssl, debug=args.debug)
    try:
        client.connect()
        print('  TCP/transport OK')
        client.login()
        print('  Login OK')
        print('  Serial Number :', client.get_serial_number())
        print('  Device Type   :', client.get_device_type())
        print('  Firmware      :', client.get_software_version())

        # Enrollment / user management branches.
        if args.get_user:
            print('Querying user %s ...' % args.get_user)
            print('  ->', client.get_access_user(args.get_user))
            return
        if args.remove_user:
            print('Removing user %s ...' % args.remove_user)
            print('  ->', 'OK' if client.remove_access_user(args.remove_user) else 'FAILED')
            return
        if args.push_user:
            print('Pushing user %s ...' % args.push_user)
            outcome = client.push_access_user(
                user_id=args.push_user,
                user_name=args.push_name or ('User %s' % args.push_user),
                card_no=args.push_card,
            )
            print('  ->', outcome)
            return

        end = int(time.time())
        start = end - args.hours * 3600
        print('Fetching records for the last %s hour(s) ...' % args.hours)
        records = client.find_access_records(start, end)
        print('  Fetched %s record(s).' % len(records))
        for rec in records[:10]:
            print('   -', rec)
        if len(records) > 10:
            print('   ... (%s more)' % (len(records) - 10))
    except DahuaRpcError as e:
        print('ERROR:', e)
        sys.exit(2)
    finally:
        if args.debug:
            print('\n--- DEBUG PROTOCOL LOG ---')
            for line in client.debug_log:
                print(line)
        client.close()


if __name__ == '__main__':
    main()
