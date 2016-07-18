#!/usr/bin/env python
# inventory.py - assist in monitoring windows-based kvm domains
import argparse
import collections
import os
import re
import Queue
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
import yaml

from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.inventory import Inventory
import libvirt
import paramiko

paramiko.util.log_to_file(os.devnull)

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
ANSIBLE_PATH = os.path.dirname(BASE_PATH)
HOST_PATH = os.path.join(ANSIBLE_PATH, "hosts")
CRED_PATH = os.path.join(ANSIBLE_PATH, "group_vars", "all.yml")

G = lambda s: "\033[92m{}\033[0m".format(s)
R = lambda s: "\033[91m{}\033[0m".format(s)

class KVMHost(object):
    def __init__(self, user, host, network="default"):
        self.hostname = host
        self.username = user
        self.conn_cmd = "qemu+ssh://{}@{}/system".format(user, host)
        self.conn = libvirt.open(self.conn_cmd)
        self.network = network
        self.nodes = []

    def get_net_hosts(self):
        """
        returns a list of dhcp lease info (mac, ip) for a given network
        """
        net = self.conn.networkLookupByName(self.network)
        devices = []
        for entry in net.DHCPLeases():
            device = {
                "mac": entry["mac"],
                "ip": entry["ipaddr"]
            }
            devices.append(device)
        return devices

    def get_mac_domain(self):
        """
        reads all kvm domain xml descriptors for lookup of mac to domain

        returns a dict of mac address keys to domain name values
        """
        domains = self.conn.listAllDomains()

        mac_to_dom = {}
        for domain in domains:
            xml = ET.fromstring(domain.XMLDesc())
            mac = xml.find("./devices/interface/mac").attrib["address"]

            mac_to_dom[mac] = domain.name()
        return mac_to_dom

    def inventory(self):
        """
        returns a list of dicts describing domain network info
        """
        dhcp_info = self.get_net_hosts()
        mac_to_dom = self.get_mac_domain()

        node_inventory = []
        # combine results
        for dom in dhcp_info:
            try:
                dom_mac = dom["mac"]
                dom["name"] = mac_to_dom[dom_mac]
                node_inventory.append(dom)
            except KeyError:
                # skip stale dhcp info
                pass
        self.nodes = sorted(node_inventory, key=lambda d: d["name"])
        return self.nodes

    def send_file(self, local_path, win_path, kvm_path, node_user=None, node_pass=None,
                  web_srv="192.168.122.1", node_name=None, execute=None):

        node_user, node_pass = self._node_creds(node_user, node_pass)

        fname = os.path.basename(local_path)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, username=self.username)

        # add filename to kvm_path
        if not kvm_path.endswith(fname):
            kvm_path = os.path.join(kvm_path, fname)

        # drop file into path
        sftp = ssh.open_sftp()
        sftp.chdir(os.path.dirname(kvm_path))
        try:
            sftp.put(local_path, kvm_path)
        except IOError as e:
            print repr(e)
            print "Failed to send file to %s with path %s, attempting to delete as root before trying again" % (self.hostname, kvm_path)
            _, stdout, stderr = ssh.exec_command("sudo rm -f {}".format(kvm_path))
            err = stderr.read()
            out = stdout.read()
            if err:
                print "[STDERR]"
                print err
            if out:
                print "[STDOUT]"
                print out
            try:
                sftp.put(local_path, kvm_path)
            except Exception as e:
                print repr(e)
                print "Failed to send file to %s with path %s again, aborting" % (self.hostname, kvm_path)
                raise

        # download files
        cmd = '(new-object system.net.webclient).downloadfile("http://{}/{}","{}"); write-host -nonewline downloaded'
        cmd = cmd.format(web_srv, fname, win_path)
        self.command_nodes(
            node_name=node_name,
            node_user=node_user,
            node_pass=node_pass,
            command=cmd
        )

        if execute is not None:
            cmd = "{} {}".format(win_path, execute)
            self.command_nodes(
                node_name=node_name,
                node_user=node_user,
                node_pass=node_pass,
                command=cmd
            )

    def view(self, node_names=None, delay=1):
        """
        run virt-viewer on target nodes
        """
        # select all nodes
        if node_names == None:
            node_names = [n["name"] for n in self.nodes if n]

        if isinstance(node_names, list):
            for node_name in node_names:
                self._view_node(node_name)
                time.sleep(delay)
        else:
            self._view_node(node_names)

    def _view_node(self, node_name):
        print "Displaying {} on {}".format(node_name, self.hostname)
        cmd = "virt-viewer -c {} {}".format(self.conn_cmd, node_name)
        with open(os.devnull, "wb") as nil:
            subprocess.Popen(cmd.split(), stdout=nil, stderr=nil)

    @property
    def node_count(self):
        return len(self.nodes)

    def command_host(self, command):
        """
        execute shell command on kvm host via ssh
        """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(self.hostname, username=self.username)
            _, stdout, stderr = ssh.exec_command(command)
            err = stderr.read()
            out = stdout.read()
            if err:
                print "[STDERR]"
                print err
            if out:
                print "[STDOUT]"
                print out
        finally:
            ssh.close()

    def _node_creds(self, node_user, node_pass):
        # default node creds
        if node_user == None or node_pass == None:
            with open(CRED_PATH, "rb") as fp:
                cred = yaml.load(fp.read(), Loader=yaml.Loader)
            node_user = cred["node_username"]
            node_pass = cred["node_password"]
            del(cred)
        return (node_user, node_pass)


    def command_nodes(self, command, node_user=None, node_pass=None, node_name=None):
        """
        execute powershell command on selected nodes via winrm
        """
        # select all nodes
        if node_name == None:
            node_name = [n["name"] for n in self.nodes if n]

        node_user, node_pass = self._node_creds(node_user, node_pass)

        if isinstance(node_name, list):
            nodes = [n for n in self.nodes if n["name"] in node_name]
            for node in nodes:
                print "{} - {} - {}".format(self.hostname, node["name"], command)
                cmd = self._winrm(
                    hostname=node["ip"],
                    username=node_user,
                    password=node_pass,
                    command=command
                )
                self.command_host(cmd)
        else:
            nodes = [n for n in self.nodes if n["ip"] == node_name]
            for node in nodes:
                print "{} - {} - {}".format(self.hostname, node["name"], command)
                cmd = self._winrm(
                    hostname=node["ip"],
                    username=node_user,
                    password=node_pass,
                    command=command
                )
                self.command_host(cmd)

    def _winrm(self, hostname, username, password, command):
        """
        wrap commands for python + pywinrm execution
        """
        wrm = []
        wrm.append("import winrm")
        w = 'print winrm.Session("{}",auth=("{}","{}")).run_ps("""{}""")'
        w = w.format(hostname, username, password, command)
        wrm.append(w)
        wrm = ";".join(wrm).strip()
        cmd = """python -c '{}'""".format(wrm)
        return cmd

    def reboot_nodes(self, node_names=None, delay=1):
        """
        graceful reboot of selected nodes with delay
        """
        # reboot all nodes
        if node_names == None:
            for dom in self.conn.listAllDomains():
                try:
                    dom.reboot()
                    print "Reboot: {} - {}".format(self.hostname, dom.name())
                except libvirt.libvirtError as e:
                    print "[-] Failed to reboot {}. {}".format(dom.name(), repr(e))
                time.sleep(delay)
            return

        if isinstance(node_names, list):
            for node_name in node_names:
                try:
                    dom = self.conn.lookupByName(node_name)
                    dom.reboot()
                    print "Reboot: {} - {}".format(self.hostname, dom.name())
                except libvirt.libvirtError as e:
                    print "[-] Failed to reboot {}. {}".format(node_name, repr(e))
                time.sleep(delay)
        else:
            try:
                dom = self.conn.lookupByName(node_names)
                dom.reboot()
            except libvirt.libvirtError as e:
                print "[-] Failed to reboot {}. {}".format(node_names, repr(e))


def ansible_inventory(hosts_path):
    ldr, vmr = DataLoader(), VariableManager()
    return Inventory(loader=ldr, variable_manager=vmr, host_list=hosts_path)


def main(args):
    # use ansible hosts file to get full kvm host + domain inventory
    inv = ansible_inventory(args.hosts_path)

    results = Queue.Queue()

    def worker(user, host):
        try:
            kvm = KVMHost(user, host)
            kvm.inventory()
            results.put(kvm)
        except libvirt.libvirtError:
            pass

    # retrieve inventory of all kvm host and domains
    threads = []
    for host in inv.get_hosts("kvm"):
        host = str(host)
        t = threading.Thread(name=host, target=worker, args=(args.user, host))
        t.start()
        threads.append(t)
    [t.join(60) for t in threads]

    inventory = {}
    while not results.empty():
        kvm = results.get()
        inventory[kvm.hostname] = kvm
    # sort by vhost
    inventory = collections.OrderedDict(sorted(inventory.iteritems(), key=lambda x: x[0]))

    if args.cli == "reboot":
        for vhost in args.vhost:
            if vhost.lower() == "all":
                for name, kvm in inventory.iteritems():
                    kvm.reboot_nodes(delay=args.delay)
            else:
                kvm = inventory[vhost]
                kvm.reboot_nodes(args.vnode, delay=args.delay)
    elif args.cli == "send":
        for vhost in args.vhost:
            if vhost.lower() == "all":
                for name, kvm in inventory.iteritems():
                    kvm.send_file(
                        node_name=None,
                        node_user=args.guest_user,
                        node_pass=args.guest_pass,
                        local_path=args.local_path,
                        win_path=args.win_path,
                        kvm_path=args.kvm_path,
                        web_srv=args.web_server,
                        execute=args.execute
                    )
            else:
                kvm = inventory[vhost]
                kvm.send_file(
                    node_name=args.vnode,
                    node_user=args.guest_user,
                    node_pass=args.guest_pass,
                    local_path=args.local_path,
                    win_path=args.win_path,
                    kvm_path=args.kvm_path,
                    web_srv=args.web_server,
                    execute=args.execute
                )
    elif args.cli == "command":
        for vhost in args.vhost:
            if vhost.lower() == "all":
                for name, kvm in inventory.iteritems():
                    kvm.command_nodes(
                        node_user=args.guest_user,
                        node_pass=args.guest_pass,
                        command=args.pshell
                    )
            else:
                kvm = inventory[vhost]
                kvm.command_nodes(
                    node_name=args.vnode,
                    node_user=args.guest_user,
                    node_pass=args.guest_pass,
                    command=args.pshell
                )
    elif args.cli == "view":
        for host, kvm in inventory.iteritems():
            for node in kvm.nodes:
                if args.hostname.upper() in node["mac"].upper().replace(":", ""):
                    kvm.view(node["name"], delay=args.delay)
    elif args.cli == "list":
        # pretty print
        node_count = 0
        host_count = 0
        to_host = lambda mac: "H-{}".format(mac.upper().replace(":", ""))
        for host, kvm in inventory.iteritems():
            host_count += 1
            if args.find is not None:
                for node in kvm.nodes:
                    mac = to_host(node["mac"])
                    if args.find.upper() in mac:
                        print "{}".format(R(host))
                        print "    {}\t{}\t{}".format(G(node["name"]), mac, node["ip"])
            else:
                print "{}".format(R(host))
                for node in kvm.nodes:
                    node_count += 1
                    mac = to_host(node["mac"])
                    print "    {}\t{}\t{}".format(G(node["name"]), mac, node["ip"])

        if args.find is None:
            print "="*50
            print "TOTAL HOSTS:\t{}".format(host_count)
            print "TOTAL NODES:\t{}".format(node_count)
    else:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--user", default="srt")
    parser.add_argument("-H", "--hosts_path", default=HOST_PATH)
    subparsers = parser.add_subparsers(dest="cli")

    send_subparser = subparsers.add_parser(
        "send",
        help="LP file is sent to KP. Fuzz nodes retrieve KP file into WP."
    )
    send_subparser.add_argument("vhost", nargs="+")
    send_subparser.add_argument("-n", "--vnode", nargs="+")
    send_subparser.add_argument("-lp", "--local-path", help="local path", required=True)
    send_subparser.add_argument("-wp", "--win-path", help="win path", required=True)
    send_subparser.add_argument("-kp", "--kvm-path", help="kvm path", default="/haka/tmp")
    send_subparser.add_argument("-e", "--execute", help="execute uploaded file with switches")
    send_subparser.add_argument("-gu", "--guest-user")
    send_subparser.add_argument("-gp", "--guest-pass")
    send_subparser.add_argument("-ws", "--web-server", default="192.168.122.1")

    reboot_subparser = subparsers.add_parser(
        "reboot",
        help="reboot fuzz nodes"
    )
    reboot_subparser.add_argument("vhost", nargs="+")
    reboot_subparser.add_argument("-n", "--vnode", nargs="+")
    reboot_subparser.add_argument("-d", "--delay", default=1, type=int)

    command_subparser = subparsers.add_parser(
        "command",
        help="run powershell on fuzz nodes"
    )
    command_subparser.add_argument("vhost", nargs="+")
    command_subparser.add_argument("-p", "--pshell")
    command_subparser.add_argument("-n", "--vnode", nargs="+")
    command_subparser.add_argument("-gu", "--guest-user")
    command_subparser.add_argument("-gp", "--guest-pass")

    view_subparser = subparsers.add_parser(
        "view",
        help="view fuzz node by hostname"
    )
    view_subparser.add_argument("hostname")
    view_subparser.add_argument("-d", "--delay", default=1, type=int)

    list_subparser = subparsers.add_parser(
        "list",
        help="list inventory"
    )
    list_subparser.add_argument("-f", "--find", help="Node hostname to find")

    args = parser.parse_args()
    main(args)
