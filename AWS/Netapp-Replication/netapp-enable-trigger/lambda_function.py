#!/usr/bin/env python3
# TriggerEnableNetAppReplication script

import os
import re
import json
import requests
from multiprocessing import Process

processes = []
enable_url = os.environ['enable_url']


def lambda_handler(event, context):
    if 'multiValueQueryStringParameters' in event and event['multiValueQueryStringParameters'] is not None and 'ax_token' in event['multiValueQueryStringParameters']:
        if os.environ['ax_token'] != event['multiValueQueryStringParameters']['ax_token'][0]:
            return {'statusCode': 500, 'body': json.dumps({'result': "token parameter 'ax_token' is incorrect"})}
    else:
        return {'statusCode': 500, 'body': json.dumps({'result': "token parameter 'ax_token' is mandatory"})}

    # If reset is unsuccessful operation is skipped
    if ('body' in event and event['body'] is not None and 'resetStatus' in event['body'] and
            json.loads(event['body'])['resetStatus'] != 'RESET_COMPLETED'):
        print("[INFO] Skipping, cause: Appranix reset is unsuccessful")
        return {
            'statusCode': 200,
            'body': json.dumps({'result': 'skipped'}),
            'multiValueHeaders': {'Content-Type': ['application/json']}
        }

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
        enable_url,
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
        print(f'[INFO] [{sys_mgr_ip}] Total relationships: ' + str(text['total_relationship']))
        print(f'[INFO] [{sys_mgr_ip}] Resumed relationships: ' + str(text['resumed_relationships']))
        print(f'[INFO] [{sys_mgr_ip}] Volumes Unmounted: ' + str(text['volumes_unmounted']))
        print(f'[INFO] [{sys_mgr_ip}] CloudWatch Log URL: ' + text['log_url'])
l

def get_sys_mgr_ips():
    return re.findall(r'[0-9]+(?:\.[0-9]+){3}', os.environ['sys_mgr_ips'])