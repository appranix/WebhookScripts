#!/usr/bin/env python3
# TriggerDisableNetAppReplication script

import os
import re
import json
import requests
from multiprocessing import Process

processes = []
disable_url = os.environ['disable_url']


def lambda_handler(event, context):
    if 'multiValueQueryStringParameters' in event and event['multiValueQueryStringParameters'] is not None and 'ax_token' in event['multiValueQueryStringParameters']:
        if os.environ['ax_token'] != event['multiValueQueryStringParameters']['ax_token'][0]:
            return {'statusCode': 500, 'body': json.dumps({'result': "token parameter 'ax_token' is incorrect"})}
    else:
        return {'statusCode': 500, 'body': json.dumps({'result': "token parameter 'ax_token' is mandatory"})}

    for sys_mgr_ip in get_sys_mgr_ips():
        # trigger_function(sys_mgr_ip)
        p = Process(target=trigger_function, args=(sys_mgr_ip,))
        processes.append(p)
        p.start()

    for process in processes:
        process.join()

    print("[INFO] Operation complete. Returning 200 [{'result': 'completed'}]")

    return {
        'statusCode': 200,
        'body': json.dumps({'result': 'completed'}),
        'multiValueHeaders': {'Content-Type': ['application/json']}
    }


def trigger_function(sys_mgr_ip):
    req = requests.post(
        disable_url,
        headers={"Content-Type": "application/json"},
        data=json.dumps({"sys_mgr_ip": sys_mgr_ip}),
        verify=False
    )
    if req.status_code != 200:
        print(f"[INFO] [{sys_mgr_ip}] Status Code: " + str(req.status_code))
        print(f"[INFO] [{sys_mgr_ip}] Text: " + req.text)
        print(f"[INFO] [{sys_mgr_ip}] Reason: " + req.reason)
        print(f"[INFO] [{sys_mgr_ip}] Ok: " + str(req.ok))
    else:
        text = json.loads(req.text)
        print(f'[INFO] [{sys_mgr_ip}] Enable operation complete')
        print(f'[INFO] [{sys_mgr_ip}] Total relationships: ' + str(text['total_relationships']))
        print(f'[INFO] [{sys_mgr_ip}] Paused relationships: ' + str(text['paused_relationships']))
        print(f'[INFO] [{sys_mgr_ip}] Broken relationships: ' + str(text['broken_relationships']))
        print(f'[INFO] [{sys_mgr_ip}] Volumes Mounted: ' + str(text['volumes_mounted']))
        print(f'[INFO] [{sys_mgr_ip}] CloudWatch Log URL: ' + text['log_url'])


def get_sys_mgr_ips():
    return re.findall(r'[0-9]+(?:\.[0-9]+){3}', os.environ['sys_mgr_ips'])
