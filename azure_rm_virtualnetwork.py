#!/usr/bin/python
#
# (c) 2016 Matt Davis, <mdavis@redhat.com>
#          Chris Houseknecht, <house@redhat.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#

from ansible.module_utils.basic import *
from ansible.module_utils.azure_rm_common import *

try:
    from msrestazure.azure_exceptions import CloudError
    from azure.common import AzureMissingResourceHttpError
    from azure.mgmt.network.models import VirtualNetwork, AddressSpace, DhcpOptions
except ImportError:
    # This is handled in azure_rm_common
    pass


DOCUMENTATION = '''
---
module: azure_rm_virtualnetwork
short_description: Manage Azure virtual networks.

description:
    - Create, update or delete a virtual networks. Allows setting and updating the available IPv4 address ranges
      and setting custom DNS servers. Use the azure_rm_subnet module to associate subnets with a virtual network.
    - For authentication with Azure you can pass parameters, set environment variables or use a profile stored
      in ~/.azure/credentials. Authentication is possible using a service principal or Active Directory user.
    - To authenticate via service principal pass subscription_id, client_id, secret and tenant or set set environment
      variables AZURE_SUBSCRIPTION_ID, AZURE_CLIENT_ID, AZURE_SECRET and AZURE_TENANT.
    - To Authentication via Active Directory user pass ad_user and password, or set AZURE_AD_USER and
      AZURE_PASSWORD in the environment.
    - Alternatively, credentials can be stored in ~/.azure/credentials. This is an ini file containing
      a [default] section and the following keys: subscription_id, client_id, secret and tenant or
      ad_user and password. It is also possible to add additional profiles. Specify the profile
      by passing profile or setting AZURE_PROFILE in the environment.

options:
    profile:
        description:
            - security profile found in ~/.azure/credentials file
        required: false
        default: null
    subscription_id:
        description:
            - Azure subscription Id that owns the resource group and storage accounts.
        required: false
        default: null
    client_id:
        description:
            - Azure client_id used for authentication.
        required: false
        default: null
    secret:
        description:
            - Azure client_secrent used for authentication.
        required: false
        default: null
    tenant:
        description:
            - Azure tenant_id used for authentication.
        required: false
        default: null
    resource_group:
        description:
            - name of resource group.
        required: true
        default: null
    address_prefixes_cidr:
        description:
            - List of IPv4 address ranges where each is formatted using CIDR notation. Required when creating
              a new virtual network or using purge_address_prefixes.
        default: null
        aliases:
            - address_prefixes
    dns_servers:
        description:
            - Custom list of DNS servers. Maximum length of two. The first server in the list will be treated
              as the Primary server. This is an explicit list. Existing DNS servers will be replaced with the
              specified list. Use the purge_dns_servers option to remove all custom DNS servers and revert to
              default Azure servers.
    location:
        description:
            - Valid azure location. Defaults to location of the resource group.
        default: resource_group location
    name:
        description:
            - name of the virtual network.
        required: true
        default: null
    purge_address_prefixes:
        description:
            - Use with state present to remove any existing address_prefixes.
        default: false
    purge_dns_servers:
        description:
            - Use with state present to remove existing DNS servers, reverting to default Azure servers. Mutually
              exclusive with dns_servers.
        default: false
    state:
        description:
            - Assert the state of the virtual network. Use 'present' to create or update and
              'absent' to delete.
        required: true
        default: present
        choices:
            - absent
            - present
    tags:
        description:
            - Dictionary of string:string pairs to assign as metadata to the object. Metadata tags on the object
              will be updated with any provided values. To remove tags use the purge_tags option.
        required: false
        default: null
    purge_tags:
        description:
            - Use to remove tags from an object. Any tags not found in the tags parameter will be removed from
              the object's metadata.
        default: false


requirements:
    - "python >= 2.7"
    - "azure >= 2.0.0"

authors:
    - "Matt Davis <mdavis@ansible.com>"
    - "Chris Houseknecht @chouseknecht"
'''

EXAMPLES = '''
    - name: Create a virtual network
      azure_rm_virtualnetwork:
        name: foobar
        resource_group: Testing
        address_prefixes_cidr:
            - "10.1.0.0/16"
            - "172.100.0.0/16"
        dns_servers:
            - "127.0.0.1"
            - "127.0.0.2"
        tags:
            testing: testing
            delete: on-exit

    - name: Delete a virtual network
      azure_rm_virtualnetwork:
        name: foobar
        resource_group: Testing
        state: absent
'''

EXAMPLE_OUTPUT = '''
{
    "changed": true,
    "check_mode": false,
    "results": {
        "address_prefixes": [
            "10.1.0.0/16",
            "172.100.0.0/16"
        ],
        "dns_servers": [
            "127.0.0.1",
            "127.0.0.3"
        ],
        "etag": "W/\"0712e87c-f02f-4bb3-8b9e-2da0390a3886\"",
        "id": "/subscriptions/3f7e29ba-24e0-42f6-8d9c-5149a14bda37/resourceGroups/Testing/providers/Microsoft.Network/virtualNetworks/my_test_network",
        "location": "eastus",
        "name": "my_test_network",
        "provisioning_state": "Succeeded",
        "tags": null,
        "type": "Microsoft.Network/virtualNetworks"
    }
}
'''

NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{1,61}[a-z0-9_]$")


def virtual_network_to_dict(vnet):
    '''
    Convert a virtual network object to a dict.
    :param vnet: VirtualNet object
    :return: dict
    '''
    results = dict(
        id=vnet.id,
        name=vnet.name,
        location=vnet.location,
        type=vnet.type,
        tags=vnet.tags,
        provisioning_state=vnet.provisioning_state,
        etag=vnet.etag
    )
    if vnet.dhcp_options and len(vnet.dhcp_options.dns_servers) > 0:
        results['dns_servers'] = []
        for server in vnet.dhcp_options.dns_servers:
            results['dns_servers'].append(server)
    if vnet.address_space and len(vnet.address_space.address_prefixes) > 0:
        results['address_prefixes'] = []
        for space in vnet.address_space.address_prefixes:
            results['address_prefixes'].append(space)
    return results


class AzureRMVirtualNetwork(AzureRMModuleBase):

    def __init__(self, **kwargs):

        self.module_arg_spec = dict(
            resource_group=dict(required=True),
            name=dict(required=True),
            state=dict(default='present', choices=['present', 'absent']),
            location=dict(type='str'),
            address_prefixes_cidr =dict(type='list', aliases=['address_prefixes']),
            dns_servers=dict(type='list',),
            purge_address_prefixes=dict(type='bool', default=False, aliases=['purge']),
            purge_dns_servers=dict(type='bool', default=False),
            log_path=dict(type='str', default='azure_rm_virtualnetwork.log'),
        )

        mutually_exclusive = [
            ('dns_servers', 'purge_dns_servers')
        ]

        required_if = [
            ('purge_address_prefixes', True, ['address_prefixes_cidr'])
        ]

        super(AzureRMVirtualNetwork, self).__init__(self.module_arg_spec,
                                                    mutually_exclusive=mutually_exclusive,
                                                    required_if=required_if,
                                                    supports_check_mode=True,
                                                    **kwargs)
        self.resource_group = None
        self.name = None
        self.state = None
        self.location = None
        self.address_prefixes_cidr = None
        self.purge_address_prefixes = None
        self.dns_servers = None
        self.purge_dns_servers = None

        self.results=dict(
            changed=False,
            check_mode=self.check_mode,
            results={}
        )

    def exec_module_impl(self, **kwargs):

        for key in self.module_arg_spec.keys() + ['tags']:
            setattr(self, key, kwargs[key])

        resource_group = self.get_resource_group(self.resource_group)
        if not self.location:
            # Set default location
            self.location = resource_group.location

        if not NAME_PATTERN.match(self.name):
            self.fail("Parameter error: name must begin with a letter or number, end with a letter, number "
                      "or underscore and may contain only letters, numbers, periods, underscores or hyphens.")

        if self.state == 'present' and self.purge_address_prefixes:
            for prefix in self.address_prefixes_cidr:
                if not CIDR_PATTERN.match(prefix):
                    self.fail("Parameter error: invalid address prefix value {0}".format(prefix))

            if self.dns_servers and len(self.dns_servers) > 2:
                self.fail("Parameter error: You can provide a maximum of 2 DNS servers.")

        changed = False
        results = dict()

        try:
            self.log('Fetching vnet {0}'.format(self.name))
            vnet = self.network_client.virtual_networks.get(self.resource_group, self.name)

            results = virtual_network_to_dict(vnet)
            self.log('Vnet exists {0}'.format(self.name))
            self.log(results, pretty_print=True)
            self.check_provisioning_state(vnet, self.state)

            if self.state == 'present':
                if self.address_prefixes_cidr:
                    existing_address_prefix_set = set(vnet.address_space.address_prefixes)
                    requested_address_prefix_set = set(self.address_prefixes_cidr)
                    missing_prefixes = requested_address_prefix_set - existing_address_prefix_set
                    extra_prefixes = existing_address_prefix_set - requested_address_prefix_set
                    if len(missing_prefixes) > 0:
                        self.log('CHANGED: there are missing address_prefixes')
                        changed = True
                        if not self.purge_address_prefixes:
                            # add the missing prefixes
                            for prefix in missing_prefixes:
                                results['address_prefixes'].append(prefix)

                    if len(extra_prefixes) > 0 and self.purge_address_prefixes:
                        self.log('CHANGED: there are address_prefixes to purge')
                        changed = True
                        # replace existing address prefixes with requested set
                        results['address_prefixes'] = self.address_prefixes_cidr

                update_tags, results['tags'] = self.update_tags(results['tags'])
                if update_tags:
                    changed = True

                if self.dns_servers:
                    existing_dns_set = set(vnet.dhcp_options.dns_servers)
                    requested_dns_set = set(self.dns_servers)
                    if existing_dns_set != requested_dns_set:
                        self.log('CHANGED: replacing DNS servers')
                        changed = True
                        results['dns_servers'] = self.dns_servers

                if self.purge_dns_servers and vnet.dhcp_options and len(vnet.dhcp_options.dns_servers) > 0:
                    self.log('CHANGED: purging existing DNS servers')
                    changed = True
                    results['dns_servers'] = []
            elif self.state == 'absent':
                self.log("CHANGED: vnet exists but requested state is 'absent'")
                changed = True
        except CloudError:
            self.log('Vnet {0} does not exist'.format(self.name))
            if self.state == 'present':
                self.log("CHANGED: vnet {0} does not exist but requested state is 'present'".format(self.name))
                changed = True

        self.results['changed'] = changed
        self.results['results'] = results

        if self.check_mode:
            return self.results

        if changed:
            if self.state == 'present':
                if not results:
                    # create a new virtual network
                    self.log("Create virtual network {0}".format(self.name))
                    if not self.address_prefixes_cidr:
                        self.fail('Parameter error: address_prefixes_cidr required when creating a virtual network')
                    vnet = VirtualNetwork(
                        location=self.location,
                        address_space=AddressSpace(
                            address_prefixes=self.address_prefixes_cidr
                        )
                    )
                    if self.dns_servers:
                        vnet.dhcp_options = DhcpOptions(
                            dns_servers=self.dns_servers
                        )
                    if self.tags:
                        vnet.tags = self.tags
                    self.results['results'] = self.create_or_update_vnet(vnet)
                else:
                    # update existing virtual network
                    self.log("Update virtual network {0}".format(self.name))
                    vnet = VirtualNetwork(
                        location=results['location'],
                        address_space=AddressSpace(
                            address_prefixes=results['address_prefixes']
                        ),
                        tags=results['tags']
                    )
                    if results['dns_servers']:
                        vnet.dhcp_options = DhcpOptions(
                            dns_servers=results['dns_servers']
                        )
                    self.results['results'] = self.create_or_update_vnet(vnet)
            elif self.state == 'absent':
                self.delete_virtual_network()

        return self.results

    def create_or_update_vnet(self, vnet):
        try:
            poller = self.network_client.virtual_networks.create_or_update(self.resource_group, self.name, vnet)
        except Exception, exc:
            self.fail("Error creating or updating virtual network {0} - {1}".format(self.name, str(exc)))

        new_vnet = self.get_poller_result(poller)

        return virtual_network_to_dict(new_vnet)

    def delete_virtual_network(self):
        try:
            poller = self.network_client.virtual_networks.delete(self.resource_group, self.name)
        except Exception, exc:
            self.fail("Error deleting virtual network {0} - {1}".format(self.name, str(exc)))
        self.get_poller_result(poller)
        # The poller does not actually return anything. If we got this far, the we'll assume
        # that the operation succeeded.
        self.results['results']['status'] = 'Deleted'
        return True


def main():
    if '--interactive' in sys.argv:
        # import the module here so we can reset the default complex args value
        import ansible.module_utils.basic

        ansible.module_utils.basic.MODULE_COMPLEX_ARGS = json.dumps(dict(
            resource_group="rm_demo",
            name='test-vnet',
            state='present',
            location='West US',
            address_prefixes_cidr=['10.0.1.0/24'],
            log_mode='stderr'
        ))

    AzureRMVirtualNetwork().exec_module()

main()

