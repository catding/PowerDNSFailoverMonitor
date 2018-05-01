#!/usr/bin/env python3

import api
import time
import yaml
import socket
import requests
import logging
from contextlib import closing

STATUS_UNKNOWN = 0
STATUS_OFFLINE = -1
STATUS_ONLINE = 1

def getRecordsForZoneMonitor(records, recordName, monitorData):
    for record in records:
        if record['name'] == recordName and record['type'] == monitorData['recordType']:
            return record
        
    return False

def checkTcpConnection(host, checkData):
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(checkData['timeout'])
        if sock.connect_ex((host, checkData['port'])) == 0:
            return STATUS_ONLINE
        else:
            return STATUS_OFFLINE
        
def checkHttpConnection (host, checkData):
    proto = 'http'
    if 'ssl' in checkData and checkData['ssl']:
        proto = 'https'
        
    if 'port' in checkData and checkData['port']:
        host = host + ':' + str(checkData['port'])
    
    try:
        data = requests.get(proto + '://' + host + checkData['uri'], headers={'host': checkData['host']}, timeout=checkData['timeout'])
        responseCode = data.status_code
        responseData = data.text
    except:
        responseCode = 500
        responseData = ''
    
    if responseCode == 200 and checkData['search'] in responseData:
        return STATUS_ONLINE
    else:
        return STATUS_OFFLINE

def testHosts(recordData, checkData):
    changed = False
    counterOffline = 0

    for recordEntry in recordData['records']:
        result = STATUS_UNKNOWN
        if checkData['type'] == 'tcp':
            result = checkTcpConnection(recordEntry['content'], checkData)
        elif checkData['type'] == 'http':
            result = checkHttpConnection(recordEntry['content'], checkData)

        if result == STATUS_ONLINE:
            lvl = logging.DEBUG
            if recordEntry['disabled']:
                lvl = logging.INFO

            logging.log(lvl, '{}: "{}" is online.'.format(recordData['name'], recordEntry['content']))
            
            if recordEntry['disabled']:
                recordEntry['disabled'] = False
                changed = True
        elif result == STATUS_OFFLINE:
            logging.info('{}: "{}" is offline.'.format(recordData['name'], recordEntry['content']))
            counterOffline = counterOffline + 1
            
            if not recordEntry['disabled']:
                recordEntry['disabled'] = True
                changed = True
        else:
            logging.info('{}: Status for "{}" is unknown.'.format(recordData['name'], recordEntry['content']))
    
    # Enable all records if all targets are offline
    if counterOffline == len(recordData['records']):
        logging.warn('Enable all records because all are offline...')
        for recordEntry in recordData['records']:
            recordEntry['disabled'] = False
            
        changed = True
    
    if changed:
        recordData['changetype'] = 'REPLACE'
        return recordData
    
    return False

if __name__ == "__main__":
    with open('config/config.yml') as fp:
        config = yaml.load(fp)
        
    if config['logging']['enabled']:
        logging.basicConfig(level=config['logging']['level'], filename=config['logging']['file'], format='[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Surpress the log messages from the requests library
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    client = api.PowerDNS(config['pdns']['apiUrl'], config['pdns']['apiSecret'])

    while (True):
        logging.debug('Check the monitors...')
        
        for zoneName, zoneMonitors in config['monitors'].items():
            zoneData = client.get_zone(zoneName)
            zoneRecords = zoneData['rrsets']

            for zoneMonitor, zoneMonitorData in zoneMonitors.items():
                recordsForMonitor = getRecordsForZoneMonitor(zoneRecords, zoneMonitor, zoneMonitorData)
                
                # We need at leasat 2 records to fail over
                if recordsForMonitor == False or len(recordsForMonitor['records']) < 2:
                    logging.info('Not enough records for the monitor "{}"...'.format(zoneMonitor))
                    continue
                
                recordData = testHosts(recordsForMonitor, zoneMonitorData['check'])
                
                if recordData != False:
                    logging.info('Send the changes in the zone "{}" to the pdns api...'.format(zoneName))
                    result = client.set_zone_records(zoneName, [recordData])

        logging.debug('Wait for the next check...')
        time.sleep(config['interval'])

