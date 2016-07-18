#!/usr/bin/env python
import argparse
import winrm


def main(args):
    cmd = "whoami"
    auth = (args.username, args.password)
    s = winrm.Session(args.hostname, auth)
    resp = s.run_ps("whoami")
    out = resp.std_out.strip()
    err = resp.std_err.strip()
    if out:
        print out
    if err:
        print err

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--username", required=True)
    parser.add_argument("-p", "--password", required=True)
    parser.add_argument("hostname")
    args = parser.parse_args()

    out = main(args)
