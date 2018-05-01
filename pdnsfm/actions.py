import logging
import subprocess
import os
import json

def executeActions(actions, data):
    for action in actions:
        logging.debug('Execute action {}.'.format(action))
        
        executeAction(action, data)
            
def executeAction(action, data):
    actionEnv = os.environ.copy()
    actionEnv['EVENT'] = json.dumps(data)
    
    commandRaw = action
    command = commandRaw.split(' ')
    
    subprocess.call(command, env=actionEnv)
        