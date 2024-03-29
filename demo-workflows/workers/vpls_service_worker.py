from __future__ import print_function

import itertools

from vpls_model import Service
import frinx_conductor_workers.uniconfig_worker
import vpls_worker
import frinx_conductor_workers.common_worker
import vll_service_worker


def default_filter_strategy():
    return common_worker.default_filter_strategy('frinx-openconfig-network-instance-types:L2VSI')


def name_filter_strategy(name):
    return common_worker.name_filter_strategy('frinx-openconfig-network-instance-types:L2VSI', name)


def vccid_filter_strategy(vccid):
    return common_worker.vccid_filter_strategy('frinx-openconfig-network-instance-types:L2VSI', vccid)


def service_create_vpls_commit(task):
    return service_create_vpls(task, "commit")


def service_create_vpls_dryrun(task):
    return service_create_vpls(task, "dry-run")


def service_create_vpls(task, commit_type):
    dryrun = bool("dry-run" == commit_type)
    add_debug_info = task['inputData']['service'].get('debug', False)
    service = Service.parse_from_task(task)

    device_ids = list(set(service.device_ids()))
    if len(device_ids) < 2:
        raise Exception("There is need to have at least 2 devices to configure vpls instance")

    ifc_responses = []
    ifc_put_responses = []
    ifc_policy_put_responses = []
    ifc_disable_stp_responses = []

    for device in service.devices:
        ifc_response = vll_service_worker.read_interface(device)
        if common_worker.task_failed(ifc_response):
            common_worker.replace_cfg_with_oper(device_ids)
            return common_worker.fail('VPLS instance: %s configuration in uniconfig FAIL. Device: %s interface %s does not exist'
                                                            % (service.id, device.id, device.interface), response=ifc_response)
        ifc_responses.append(ifc_response)

        if not dryrun and device.interface_reset:
            policy = vll_service_worker.read_interface_policy(device)
            if not common_worker.task_failed(policy):
                ifc_delete_policy = vll_service_worker.delete_interface_policy(device)
                if ifc_delete_policy is not None and common_worker.task_failed(ifc_delete_policy):
                    common_worker.replace_cfg_with_oper([device.id])
                    return common_worker.fail('VPLS instance: %s configuration in uniconfig FAIL. Device: %s interface policy %s cannot be reset'
                                              % (service.id, device.id, device.interface),
                                              response=ifc_delete_policy)

            ifc_delete_response = vll_service_worker.delete_interface(device)
            if common_worker.task_failed(ifc_delete_response):
                common_worker.replace_cfg_with_oper([device.id])
                return common_worker.fail('VPLS instance: %s configuration in uniconfig FAIL. Device: %s interface %s cannot be reset'
                                          % (service.id, device.id, device.interface),
                                          response=ifc_delete_response)

            response_commit = common_worker.commit([device.id])

            # Check response from commit RPC. The RPC always succeeds but the status field needs to be checked
            if common_worker.task_failed(response_commit) or common_worker.uniconfig_task_failed(response_commit):
                common_worker.replace_cfg_with_oper([device.id])
                return common_worker.fail('VPLS instance: %s commit for interface reset FAIL' % service.id,
                                          response_commit=response_commit)

            response_sync_from_net = common_worker.sync_from_net([device.id])

            # Check response from commit RPC. The RPC always succeeds but the status field needs to be checked
            if common_worker.task_failed(response_sync_from_net) or common_worker.uniconfig_task_failed(response_sync_from_net):
                common_worker.replace_cfg_with_oper([device.id])
                return common_worker.fail('VPLS instance: %s sync_from_network after interface reset FAIL' % service.id,
                                          response_sync_from_net=response_sync_from_net)

        ifc_put_response1 = vll_service_worker.put_interface(service, device)
        if common_worker.task_failed(ifc_put_response1):
            common_worker.replace_cfg_with_oper(device_ids)
            return common_worker.fail('VPLS instance: %s configuration in uniconfig FAIL. Device: %s interface %s cannot be configured'
                                                            % (service.id, device.id, device.interface), response=ifc_put_response1)
        ifc_put_responses.append(ifc_put_response1)

        ifc_policy_put_response1 = vll_service_worker.put_interface_policy(device)
        if ifc_policy_put_response1 is not None and common_worker.task_failed(ifc_policy_put_response1):
            common_worker.replace_cfg_with_oper(device_ids)
            return common_worker.fail('VPLS instance: %s configuration in uniconfig FAIL. Device: %s interface policies %s cannot be configured'
                                                            % (service.id, device.id, device.interface), response=ifc_policy_put_response1)
        if ifc_policy_put_response1 is not None:
            ifc_policy_put_responses.append(ifc_policy_put_response1)

        ifc_stp_delete_response1 = vll_service_worker.disable_interface_stp(device)
        # return common_worker.fail('VPLS instance: %s configuration in uniconfig FAIL. Device: %s interface STP %s cannot be configured'
        #                           % (service.id, device.id, device.interface), response_delete_stp=ifc_stp_delete_response1)
        # ifc_disable_stp_responses.append(ifc_stp_delete_response1)

    response_create = service_create_vpls_instance(task)
    if common_worker.task_failed(response_create):
        common_worker.replace_cfg_with_oper(device_ids)
        return common_worker.fail('VPLS instance: %s configuration in uniconfig FAIL' % service.id, response=response_create)

    # Check response from dryrun RPC. The RPC always succeeds but the status field needs to be checked
    if dryrun:
        response = common_worker.dryrun_commit(device_ids)
        return common_worker.dryrun_response('VPLS instance: %s dry-run FAIL' % service.id, add_debug_info,
                                      response_interface=ifc_put_responses,
                                      response_interface_policy=ifc_policy_put_responses,
                                      response_stp_interface_policy=ifc_disable_stp_responses,
                                      response_network_instance=response_create,
                                      response_dryrun=response)
    else:
        response = common_worker.commit(device_ids)
        return common_worker.commit_response(device_ids, 'VPLS instance: %s commit FAIL' % service.id, add_debug_info,
                                      response_interface=ifc_put_responses,
                                      response_interface_policy=ifc_policy_put_responses,
                                      response_stp_interface_policy=ifc_disable_stp_responses,
                                      response_network_instance=response_create,
                                      response_commit=response)


def service_create_vpls_instance(task):
    service = Service.parse_from_task(task)

    responses = []
    for dev_id in set(service.device_ids()):
        if dev_id == "UNKNOWN":
            continue

        task = {'inputData': {
            'id': dev_id,
            'service_id': service.id,
            'vccid': service.vccid,
            'interface': [],
            'remote_ip': [],
            'mtu': service.mtu if service.mtu is not None else 0
        }}
        for device in service.devices:
            if device.id == dev_id:
                task['inputData']['interface'].append({
                    'interface': device.interface,
                    'vlan': device.vlan,
                    'untagged': device.untagged
                })
            else:
                if device.remote_ip == "UNKNOWN":
                    continue
                task['inputData']['remote_ip'].append(device.remote_ip)

        response1 = vpls_worker.device_create_vpls(task)
        if common_worker.task_failed(response1):
            response1_delete = remove_device_vpls(dev_id, service.id)
            return common_worker.fail('VPLS instance: %s configuration in uniconfig FAIL' % service.id, response_for_rollback=response1_delete, response=response1)
        responses.append(response1)

    return common_worker.complete('VPLS instance: %s configured in uniconfig successfully' % service.id, responses=responses)


def remove_device_vpls(device_id, service_id):
    return vpls_worker.device_delete_vpls({'inputData': {
        'id': device_id,
        'service_id': service_id
    }})


def service_delete_vpls_commit(task):
    return service_delete_vpls(task, "commit")


def service_delete_vpls_dryrun(task):
    return service_delete_vpls(task, "dry-run")


def service_delete_vpls(task, commit_type):
    dryrun = bool("dry-run" == commit_type)
    add_debug_info = task['inputData']['service'].get('debug', False)

    service_id = task['inputData']['service']['id']
    services = read_remote_services({'inputData': {
        'datastore': 'actual',
        'reconciliation': 'name',
        'name': service_id
    }})

    number_of_services = len(services)
    if number_of_services < 1:
        return common_worker.fail("VPLS instance: %s does not exists" % service_id)
    if number_of_services > 1:
        return common_worker.fail("VPLS instance: %s is not unique. It occurs %s times." % (service_id, number_of_services))

    service = services[0]
    device_ids = list(set(service.device_ids()))
    response_del = service_delete_vpls_instance({'inputData': {
        'service': service.to_dict()
    }})
    if common_worker.task_failed(response_del):
        common_worker.replace_cfg_with_oper(device_ids)
        return common_worker.fail('VPLS instance deletion: %s configuration in uniconfig FAIL' % service.id, response=response_del)

    if dryrun:
        response = common_worker.dryrun_commit(device_ids)
        return common_worker.dryrun_response('VPLS instance deletion: %s dry-run FAIL' % service.id, add_debug_info,
                                             response_delete=response_del,
                                             response_dryrun=response)
    else:
        response = common_worker.commit(device_ids)
        return common_worker.commit_response(device_ids, 'VPLS instance deletion: %s commit FAIL' % service.id, add_debug_info,
                                             response_delete=response_del,
                                             response_commit=response)


def service_delete_vpls_instance(task):
    service = Service.parse_from_task(task)

    responses = []
    for dev_id in set(service.device_ids()):
        response1 = remove_device_vpls(dev_id, service.id)
        if common_worker.task_failed(response1):
            return common_worker.fail('VPLS instance: %s removal in uniconfig FAIL' % service.id, response=response1)
        responses.append(response1)

    return common_worker.complete('VPLS instance: %s removed in uniconfig successfully' % service.id, responses=responses)


def device_add_to_vpls_commit(task):
    return device_add_to_vpls(task, "commit")


def device_add_to_vpls_dryrun(task):
    return device_add_to_vpls(task, "dry-run")


def device_add_to_vpls(task, commit_type):
    vpls_config = read_remote_services(task)

    service = create_device_add_to_vpls(task, vpls_config)

    add_debug_info = task['inputData']['service'].get('debug', False)

    task = {
        "inputData": {
            "service": service.to_dict()
        }
    }

    response_vpls = service_create_vpls_instance(task)
    dryrun = bool("dry-run" == commit_type)

    device_ids = list(set(service.device_ids()))
    if dryrun:
        response = common_worker.dryrun_commit(device_ids)
        return common_worker.dryrun_response('VPLS instance: %s dry-run FAIL' % service.id, add_debug_info,
                                             response_vpls=response_vpls, response_dryrun=response)
    else:
        response = common_worker.commit(device_ids)
        return common_worker.commit_response(device_ids, 'VPLS instance: %s commit FAIL' % service.id, add_debug_info,
                                             response_vpls=response_vpls, response_commit=response)


def create_device_add_to_vpls(task, vpls_config):
    service = filter(lambda s: s.id == task['inputData']['service']['id'], vpls_config)
    if len(service) < 1:
        raise Exception("VPLS '%s' does not exist." % task['inputData']['service']['id'])
    service = service[0]
    service.devices.extend(Service.parse_devices(task['inputData']['service']['devices']))

    return service


def device_delete_from_vpls_commit(task):
    return device_delete_from_vpls(task, "commit")


def device_delete_from_vpls_dryrun(task):
    return device_delete_from_vpls(task, "dry-run")


def device_delete_from_vpls(task, commit_type):
    vpls_config = read_remote_services(task)

    service = create_device_delete_from_vpls(task, vpls_config)

    responses_remove = []
    remove_ids = list(set(dev['id'] for dev in task['inputData']['service']['devices']))
    for dev_id in remove_ids:
        response_remove = remove_device_vpls(dev_id, service.id)
        if common_worker.task_failed(responses_remove):
            return response_remove
        responses_remove.append(response_remove)

    device_ids = list(set(service.device_ids())) + remove_ids

    add_debug_info = task['inputData']['service'].get('debug', False)

    task = {
        "inputData": {
            "service": service.to_dict()
        }
    }

    response_vpls = service_create_vpls_instance(task)
    dryrun = bool("dry-run" == commit_type)

    if dryrun:
        response = common_worker.dryrun_commit(device_ids)
        return common_worker.dryrun_response('VPLS instance: %s dry-run FAIL' % service.id, add_debug_info,
                                             response_remove=responses_remove, response_vpls=response_vpls, response_dryrun=response)
    else:
        response = common_worker.commit(device_ids)
        return common_worker.commit_response(device_ids, 'VPLS instance: %s commit FAIL' % service.id, add_debug_info,
                                             response_remove=responses_remove, response_vpls=response_vpls, response_commit=response)


def create_device_delete_from_vpls(task, vpls_config):
    service = filter(lambda s: s.id == task['inputData']['service']['id'], vpls_config)
    if len(service) < 1:
        raise Exception("VPLS '%s' does not exist." % task['inputData']['service']['id'])
    service = service[0]

    ids = set(d['id'] for d in task['inputData']['service']['devices'])
    service.devices = filter(lambda d: d.id not in ids, service.devices)
    if len(service.devices) < 2:
        raise Exception('VPLS must have at least 2 devices left')

    return service


def service_read_all(task):
    remote_services = read_remote_services(task)

    services = map(lambda service: service.to_dict(), remote_services)
    return common_worker.complete('VPLS instances found successfully: %s' % len(services), services=services)


def read_remote_services(task):
    datastore = task['inputData'].get('datastore', 'actual')
    strategy, reconciliation = get_filter_strategy(task)
    if datastore not in ['intent', 'actual']:
        raise Exception('Unable to read uniconfig datastore: %s' % datastore)

    response = uniconfig_worker.execute_read_uniconfig_topology_operational(task) if datastore == 'actual' \
        else uniconfig_worker.execute_read_uniconfig_topology_config(task)

    if common_worker.task_failed(response):
        raise Exception('Unable to read uniconfig', response=response)
    if reconciliation not in ['name', 'vccid']:
        raise Exception('Unable to reconcile with strategy: %s' % reconciliation)

    if 'node' not in response['output']['response_body']['topology'][0]:
        raise Exception("Uniconfig topology is empty.")

    uniconfig_nodes = response['output']['response_body']['topology'][0]['node']

    remote_services = []
    for node in map(lambda n: (n['node-id'], extract_network_instances(n, strategy)), uniconfig_nodes):

        node_id = node[0]
        l2vsis = node[1][0]
        default_ni = node[1][1]
        ifcs = node[1][2]
        if len(l2vsis) is 0:
            continue

        for l2vsi in l2vsis:
            service = Service.parse_from_openconfig_network(node_id, l2vsi, default_ni, ifcs)
            if service is not None:
                remote_services.append(service)

    remote_services = aggregate_l2vsi_remote(remote_services) if reconciliation == 'name' \
        else aggregate_l2vsi_remote(remote_services, lambda s: s.vccid)

    return remote_services


def get_filter_strategy(task):
    reconciliation = task['inputData'].get('reconciliation', 'name')
    filter_by = task['inputData'].get(reconciliation, '')
    strategy = default_filter_strategy() if filter_by == '' else (name_filter_strategy(filter_by) if reconciliation == 'name' else vccid_filter_strategy(filter_by))
    return strategy, reconciliation


def aggregate_l2vsi_remote(remote_services, by_key=lambda remote_service: remote_service.id):
    remote_services.sort(key=by_key)
    grouped_by_name = itertools.groupby(remote_services, by_key)
    grouped_by_name_as_list = map(lambda g: list(g[1]), grouped_by_name)
    remote_services_aggregated = map(lambda l: reduce(lambda l1, l2: l1.merge(l2), l), grouped_by_name_as_list)
    return remote_services_aggregated


def extract_network_instances(node, strategy):
    networks = node['frinx-uniconfig-topology:configuration']['frinx-openconfig-network-instance:network-instances']['network-instance']
    l2vsi = filter(strategy, networks)
    default_ni = filter(lambda ni: ni['name'] == 'default', networks)[0]
    interfaces = filter(lambda i: i['config']['type'] == 'iana-if-type:ethernetCsmacd', node['frinx-uniconfig-topology:configuration']['frinx-openconfig-interfaces:interfaces']['interface'])
    return l2vsi, default_ni, interfaces


def start(cc):
    print('Starting VPLS service workers')

    # Service level configuration (spanning multiple devices)

    cc.register('VPLS_service_create', service_create_vpls_instance)

    cc.register('VPLS_service_delete', service_delete_vpls_instance)

    # Batch reconciliation from per device info into service objects

    cc.register('VPLS_service_read_all', service_read_all)

    # Below are higher order workers (which actually implement a workflow)

    cc.register('VPLS_service_commit', service_create_vpls_commit)

    cc.register('VPLS_service_dryrun', service_create_vpls_dryrun)

    cc.register('VPLS_service_delete_commit', service_delete_vpls_commit)

    cc.register('VPLS_service_delete_dryrun', service_delete_vpls_dryrun)

    cc.register('VPLS_add_device_commit', device_add_to_vpls_commit)

    cc.register('VPLS_add_device_dryrun', device_add_to_vpls_dryrun)

    cc.register('VPLS_delete_device_commit', device_delete_from_vpls_commit)

    cc.register('VPLS_delete_device_dryrun', device_delete_from_vpls_dryrun)
