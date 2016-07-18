# gunsen

Ansible playbooks and scripts to manage KVM-based infrastructure.

## Prerequisites
- Modify variables:
  - group_vars/gunsen.yml - gunsen general variables (node specs)
  - group_vars/all.yml - credentials for systems

## Workflow
1. Install - installation of roles/components
2. Prepare - prepare golden image (install client/applications, updates, etc)
3. Deploy - deploy golden image, build overlays, and define KVM domains
4. Cleanup - delete overlays and undefine KVM domains

(note) Push-File has been moved to the `inventory.py` script

# Management
Ansible playbooks to manage internal infrastructure such as:
  - Installation
    - Manager
    - Tasker
    - Datastore
    - KVM
  - KVM domain management
    - image preparation and deployment
    - qcow2 overlay generation
    - domain XML templating
  - System management
    - centralized configuration
    - updates and cleanup

## Install (install.yml)
Used for installing roles.
  - manager
  - kvm
  - tasker
  - datastore

Use ansible tags to specify which roles to install, or omit for all:
```
ansible-playbook install.yml --list-tags
ansible-playbook install.yml --tags kvm,manager,tasker,datastore

ansible-playbook install.yml
```

### kvm
```
ansible-playbook install.yml --tags kvm
```

It is possible to have multiple fuzz servers. Add each device
into the hosts file to reflect the ip address, node_count, and node_name
```
# ... omit ...

[kvm]
10.0.0.1  node_count=2 name=node-1
10.0.0.2  node_count=5 name=node-2
```
`node_count` = number of VMs to create in the fuzz server.
`name` = unique identifier used to determine kvm hostname.

Modify the ./group_vars/gunsen.yml file for the KVM domain specs.
```
# ... omit ...

node_vmem: "1024"
node_vcpu: "1"
```
`node_vmem` = virtual memory in MB.
`node_vcpu` = number of virtual cpus.

### manager, tasker, datastore
```
ansible-playbook install.yml --tags manager,tasker,datastore
```

## Prepare (prepare.yml)
(see prepare.py)
Configures the base image and runs in local KVM. Verify
the ip address of the KVM domain (ipconfig) and limit (-l)
the playbook only to the identified ip address.

(note) use inventory/prepare.py as a dynamic inventory for
  local KVM domains this should use BASE-1 as the domain
  name for the golden image and no longer requires limit (-l)
```
ansible-playbook prepare.yml -i inventory/prepare.py
```

By default, a client will not be re-installed. This
requires defining a `client` variable.

Modification of the `roles/do.prepare/tasks.client.yml` can be performed
to include the installation/management of other project-specific clients.
```
ansible-playbook prepare.yml -i inventory/prepare.py -e "client=1"
```

To reduce the amount of time for building/preparing a base image,
by default, no zeroizing and image compression is performed. In
order to force the system to compress (which takes much longer),
define the `compress` variable.
```
ansible-playbook prepare.yml -i inventory/prepare.py -e "compress=1"
```

## Deploy (deploy.yml)
Applies only to KVM hosts.
  - generates overlays based on `node_count`
  - generates KVM domain XML templates
  - defines and starts KVM domains
  - allows for pushing of files to nodes

The deploy.yml playbook can be used with an additional variable
in order to force an install. This prevents re-running overlay
and domain creation when the base image has not been modified.
```
ansible-playbook deploy.yml
```

## Cleanup (cleanup.yml)
  - destroy and undefine KVM domains
  - deletes overlay files and XML templates

The cleanup.yml playbook will destroy all the kvm domains. The
```
ansible-playbook cleanup.yml
```

To delete the contents of the working directory, including
any base images and templates, define the `wipe` variable.
```
ansible-playbook cleanup.yml -e "wipe=1"
```

## Miscellaneous

### Scripts
`bootstrap.py`
  - prepares ubuntu server for ansible management

`kvm_cleanup.py`
  - cleanup script copied and executed on remote hosts

`kvm_create.py`
  - populates template XML descriptions for KVM domains and creates KVM domain

`template.py`
  - modifies XMLDesc for KVM domain into a generic template

`inventory.py`
  - collection of useful commands for monitoring and controlling fuzz nodes
  - list KVM nodes, open console, reboot nodes, run commands, and send files

`webvirt.py`
  - mini flask server that exposes some basic libvirt commands to KVM domains


### Running stack locally (within KVM)
```
ansible-playbook -i inventory/localhost install.yml

ansible-playbook -i inventory/localhost prepare.yml -l 192.168.122.100 -e 'tasking_address=192.168.122.1 datastore_address=192.168.122.1 testfiles_address=192.168.122.1 client=1'

ansible-playbook -i inventory/localhost deploy.yml -e 'node_vcpu=1 node_vmem=1024'
```
