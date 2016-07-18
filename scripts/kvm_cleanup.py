#!/usr/bin/env python
# kvm_cleanup.py - connects to local qemu via libvirt and removes artifacts
import argparse
import os

import libvirt

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CONNECTION = libvirt.open("qemu:///system")

def destroy_undefine_domains(conn, name):
    for dom in conn.listAllDomains():
        name = dom.name()
        if name.startswith(("BASE", name)):
            try:
                dom.destroy()
            except libvirt.libvirtError:
                # domain already stopped
                pass

            try:
                dom.undefine()
            except libvirt.libvirtError:
                # domain config already removed
                pass

def delete_overlay_templates(path, wipe=False):
    base = os.path.abspath(path)
    for item in os.listdir(path):
        full = os.path.join(base, item)
        if wipe:
            try:
                os.remove(full)
            except OSError:
                pass
        else:
            if item.endswith((".ovl", ".xmlovl")):
                os.remove(full)

def main(args):
    destroy_undefine_domains(CONNECTION, name=args.name)
    delete_overlay_templates(
        path = args.path,
        wipe = args.wipe
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--path", default=BASE_PATH)
    parser.add_argument("-w", "--wipe", action="store_true")
    parser.add_argument("-n", "--name", default="haka")
    args = parser.parse_args()

    main(args)
