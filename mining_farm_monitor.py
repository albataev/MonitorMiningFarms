from pexpect import pxssh
import json, smtplib
from datetime import datetime as dt
import time
import requests
import traceback

with open('mining.json') as f:
    DATA = json.load(f)

# 0 {'gpuid': 0, 'cudaid': 0, 'busid': '0000:03:00.0', 'name': 'GeForce GTX 1080 Ti', 'gpu_status': 2, 'solver': 0, 'temperature': 77, 'gpu_power_usage': 206, 'speed_sps': 701, 'accepted_shares': 194, 'rejected_shares': 0, 'start_time': 1527891936}
from network_socket import NetworkSocket


eth008 = NetworkSocket()


def connect(ip, port, password):
    return eth008.connect_socket(ip, port, password)


def disconnect():
    eth008.close_socket()


def reboot(relay):
    pulse_time = '\xC8' # xC8 - 200ms; x64 - 100ms; x32 - 50ms; x14 - 20ms
    eth008.write('{}{}{}'.format('\x20', chr(int(relay)), pulse_time))
    get_states()


def get_states():
    eth008.write('\x24')          # send command and read back responce byte
    states = eth008.read(1)
    str_states = 'Relay states 8->1 : ' + ''.join('{0:08b}'.format(ord(x), 'b') for x in states)
    print(str_states)
    return str_states


def send_mail(mail_conn_data, msg_header, msg_body):
    msg = "\r\n".join([
      "From: {}".format('albataev@gmail.com'),
      "To: {}".format('albataev@icloud.com'),
      "Subject: {}".format(msg_header),
      'Body: ', f'\n{msg_body}'
      ])
    print('EMAIL ALERT:>>>>>>>\n', msg_header, msg_body)
    try:
        server = smtplib.SMTP(f'{mail_conn_data["smtp_server"]}:{mail_conn_data["smtp_port"]}')
        server.starttls()
        server.login(mail_conn_data['username'],mail_conn_data['password'])
        server.sendmail(mail_conn_data['fromaddr'], mail_conn_data['toaddr'], msg)
        server.quit()
    except Exception:
        pass

def hard_reset(rig):
    if rig.maintenance == 0:
        if rig.stuckGpuCount > 1 or rig.connErrorCount > 2:
            print('========HARD RESET')
            connect('92.38.195.170', 17494, 'Cassiopeia')
            reboot(rig.id[2])
            disconnect()
        if rig.stuckGpuCount == 1:
            print('========SOFT RESET')
            rig.soft_reset()
    else:
        print('RESET CALLED BUT RIG{} ON MAINTENANCE'.format(rig.id))


def calculate_profit(currency_list):
    res = {}

    def calculate(currdata, bitcoinrate, hashrate=1450000):
        for curr in currency_list:
            res[curr] = {}
            myBlockTimeSeconds = float(currdata[curr]['nethash']) * float(currdata[curr]['block_time']) / (hashrate * 1000)
            myBlockTimeDays = myBlockTimeSeconds / 86400
            res[curr]['profitPerDay'] = float(currdata[curr]['block_reward24']) / myBlockTimeDays
            res[curr]['profitPerMonth'] = res[curr]['profitPerDay'] * 30
            res[curr]['USDPerMonth'] = res[curr]['profitPerMonth'] * float(currdata[curr]['exchange_rate']) * float(bitcoinrate)
    try:
        whattomine = requests.get('http://whattomine.com/coins.json')
        bittrexBtcRate = requests.get('https://bittrex.com/api/v1.1/public/getticker?market=USDT-BTC').json()['result']['Last']
        calculate(whattomine.json()['coins'], bittrexBtcRate)
    except Exception as e:
        print('error in query API: ', e)
    return res


class Rig(object):
    def __init__(self, id, ip, port, username, password, gpu_amount, hashrate, apiAddr='localhost', apiPort=3333):
        self.ip = ip
        self.id = id
        self.port = port
        self.username = username
        self.password = password
        self.gpu_amount = gpu_amount
        self.hashrate = hashrate
        #ZCASH
        self.queryLine = '{}{} {}'.format("echo '{\"id\":0,\"jsonrpc\":\"2.0\",\"method\":\"miner_getstat1\"}' | netcat ",
                                              apiAddr, apiPort)
        self.rebootLine = '{}'.format('/home/ss/reboot_script')
        self.data = {
        'error': False,
        'curData': ''
        }
        self.error = {}
        self.s = None
        self.maintenance = 0
        self.stuckGpuCount = 0
        self.overheatCount = 0
        self.connError = False
        self.connErrorCount = 0
        self.tempAlert = 0
        self.tempAlertSent = 0
        self.hashAlert = 0
        self.hashAlertSent = 0
        self.serializeMinerResponseAlert = 0
        self.serializeMinerResponseAlertSent = 0
        self.gpuNumberAlert = 0
        self.gpuNumberAlertSent = 0
        self.message_body = ''
        self.getDataAlert = 0
        self.getDataAlertSent = 0
        self.getDataErrorText = ''
        self.error_text = ''
        self.resetCount = 0
        self.alertSent = 0
        self.errorTypes = ['connError', 'disconnectError', 'getMinerData', 'emptyMinerResponse',
                           'serializeMinerResponse', 'fillAPIData', 'gpuNumber', 'overHeat', 'stuckGpu']
        self.init_error_data()

    def init_error_data(self):
        self.error = {x: {
            'status': False,
            'alertSent': False,
            'info': ''
        } for x in self.errorTypes}

    def reset_error_data(self, errorType):
        self.error[errorType] = {
            'status': False,
            'alertSent': False,
            'info': ''
        }

    def fill_error_data(self, errorType, info):
        print('Filling error: ', errorType)
        self.error[errorType]['status'] = True
        self.error[errorType]['info'] = str(info)
        print(self.error[errorType])

    def reset_api_data(self):
            self.data['api'] = {
                'uptime': 0,
                'hashrate': 0,
                'gpu_rate': 0,
                'temperature': 0,
                'gpu_online': 0
            }

    def connect(self):
        self.s = pxssh.pxssh()
        self.connError = False
        try:
            self.s.login(server=self.ip, username=self.username, password=self.password, port=self.port, login_timeout=10, sync_multiplier=4)
            self.connErrorCount = 0
            self.reset_error_data('connError')
        except Exception as e:
            self.fill_error_data('connError', traceback.format_exc())
            self.connError = True

    def disconnect(self):
        if not self.error['connError']['status']:
            try:
                self.s.logout()
                self.s.close()
                self.reset_error_data('disconnectError')
            except Exception as e:
                self.fill_error_data('disconnectError', traceback.format_exc())
        self.s = None

    def run_command(self, console_command):
        if not self.error['connError']['status']:
            try:
                self.s.sendline(console_command)
                self.s.prompt()  # match the prompt
                consoleData = self.s.before.decode()
                return consoleData
            except Exception as e:
                print('RIG {} Execute console command error: '. format(self.id), traceback.format_exc())

    def get_miner_data(self):
        self.reset_api_data()
        if not self.error['connError']['status']:
            try:
                self.s.sendline(self.queryLine)
                self.s.prompt()  # match the prompt
                self.data['curData'] = self.s.before.decode()
                self.data['api'] = {
                    'uptime': self.data["curData"][1],
                    'hashrate': int(self.data['curData'][2].split(';')[0]),
                    'gpu_rate': self.data['curData'][3].split(';'),
                    'temperature': [int(x) for index, x in enumerate(self.data['curData'][6].split(';')) if index%2 == 0],
                    'gpu_online': len(self.data['curData'][3].split(';'))
                }
                with open('/Users/albataev/test_resp.txt', 'r') as f:
                    self.data['curData'] = f.readlines()
                self.reset_error_data('getMinerData')
            except Exception as e:
                self.fill_error_data('getMinerData', traceback.format_exc())

    def get_host_data(self):
        # get ubuntu host data
        try:
            now = dt.now()
            tz_fix = 3 * 60 * 60
            miner_up_data = self.run_command(
                "tmux ls -F '#{session_name} #{session_created}' | grep 'mining'").split('\n')[1]
            if len(miner_up_data) > 0:
                miner_start_time = dt.utcfromtimestamp(int(miner_up_data.split(' ')[1].rstrip()) + tz_fix)
            else:
                miner_start_time = 0
            host_start_time = self.run_command("uptime -s").split('\n')[1].rstrip()
            rig_uptime = now - dt.strptime(host_start_time, "%Y-%m-%d %H:%M:%S")
            miner_uptime =  now - miner_start_time
        except Exception as e:
            print('exception', traceback.format_exc())

    def process_data(self):
        # reqursts to get miner data
        data = self.data['curData']
        if data != '':
            self.reset_error_data('emptyMinerResponse')
            try:
                jsonData = json.loads(data[2])['result']
                self.reset_error_data('serializeMinerResponse')
                try:
                    self.data['api'] = {
                        'uptime': int(jsonData[1]),
                        'hashrate': int(jsonData[2].split(';')[0]),
                        'gpu_rate': [int(x) for x in jsonData[3].split(';')],
                        'temperature': [int(x) for index, x in enumerate(jsonData[6].split(';')) if index%2 == 0],
                        'gpu_online': len(jsonData[3].split(';'))
                    }
                    self.reset_error_data('fillAPIData')
                except Exception as e:
                    self.fill_error_data('fillAPIData', traceback.format_exc())
            except Exception:
                self.fill_error_data('serializeMinerResponse', traceback.format_exc())
        else:
            self.fill_error_data('emptyMinerResponse', 'Empty response from miner received. Rig{}'.format(self.id))

    def soft_reset(self):
        #NO ERROR STATUS
        self.connect()
        if not self.error['connError']['status']:
            try:
                self.s.sendline(self.rebootLine)
                self.s.prompt()  # match the prompt
                self.data['curData'] = self.s.before.decode()  # get everything before the prompt.
                print(self.data['curData'])
            except Exception as e:
                self.data['error'] = e
                return self.data
        self.disconnect()
        self.resetCount += 1

    def check_gpu_number(self):
        if self.data['api']['gpu_online'] < self.gpu_amount:
            error_text = 'NOT ALL GPUS ARE ONLINE: {} from {}'.format(self.data['api']['gpu_online'],
                                                                           self.gpu_amount)
            self.fill_error_data('gpuNumber', error_text)
            self.gpuNumberAlert = 1
        else:
            self.reset_error_data('gpuNumber')

    def check_temperature(self):
        self.overheatCount = 0
        error_text = ''
        for gpu_index, temperature in enumerate(self.data['api']['temperature']):
            if temperature > 75:
                error_text += '\nGPU#{} temperature: {}'.format(gpu_index, temperature)
                self.overheatCount += 1
                self.tempAlert = 1
                self.fill_error_data('overHeat', 'GPU#{} temperature: {}'.format(gpu_index, temperature))
        if self.overheatCount == 0:
            self.reset_error_data('overHeat')
            self.tempAlert = 0
            self.tempAlertSent = 0
        else:
            self.fill_error_data('overHeat', error_text)

    def check_hashrate(self):
        self.stuckGpuCount = 0
        error_text = ''
        for gpu_index, hashrate in enumerate(self.data['api']['gpu_rate']):
            if hashrate == 0:
                error_text += '\nGPU#{} {}; DRIVER# {}'.format(gpu_index, hashrate, gpu_index)
                self.stuckGpuCount += 1
                self.hashAlert = 1
        if self.stuckGpuCount == 0:
            self.reset_error_data('stuckGpu')
            self.hashAlert = 0
            self.hashAlertSent = 0
        else:
            self.fill_error_data('stuckGpu', error_text)

    def check_rig_health(self):
        if self.getDataAlert == 0:
            if int(self.data['api']['uptime']) > 2: # check uptime of miner after reset - to start and fill DAG files etc...
                self.check_hashrate()
                self.check_temperature()
            else: #just restarted. validate active gpus vs onboard
                self.check_gpu_number()
        if self.getDataAlert == 0 and self.getDataAlertSent == 1:
            self.getDataErrorAlertSent = 0

    def get_status(self):
        return 'RIG{}. RefRate:{}. CurrRate:{}. Uptime:{}. Resets:{}'.\
            format(self.id, self.hashrate, self.data['api']['hashrate'], self.data['api']['uptime'], self.resetCount)


def get_miner_uptime(command_line_data):
    data_to_process = command_line_data.split('\n')[1]
    sessionStartedFrom = 0
    if len(data_to_process) > 0:
        sessionStartedFrom = int(data_to_process.split(' ')[1])
    return sessionStartedFrom


if __name__ == "__main__":
    iter = 0
    farmHashrate = 0
    resetErrorsList = ['emptyMinerResponse',
                            'serializeMinerResponse', 'fillAPIData', 'gpuNumber', 'overHeat', 'stuckGpu']
    rigs_list = [Rig(id=DATA['rigs'][rig]['id'], ip=DATA['rigs'][rig]['ip'],
                     port=DATA['rigs'][rig]['port'], username=DATA['rigs'][rig]['login'],
                     password=DATA['rigs'][rig]['password'], gpu_amount=DATA['rigs'][rig]['gpu_amount'],
                     hashrate=DATA['rigs'][rig]['hashrate']) for rig in DATA['rigs']]
    r = rigs_list[0]
    print('rig', r.id)
    while True:
        farmHashrate = 0
        miningData = '{}\n'.format(time.strftime('%X %x %Z'))
        r.connect()
        r.get_host_data()
        r.get_miner_data()
        r.process_data()
        r.disconnect()
        miningData += r.get_status() + '\n'
        farmHashrate += r.data['api']['hashrate']
        for errorType in r.errorTypes:
            if r.error[errorType]['status'] and not r.error[errorType]['alertSent']:
                send_mail(DATA['email'], f'Rig{r.id} alert: {errorType}', r.error[errorType]['info'])
                r.error[errorType]['alertSent'] = True
                if errorType in resetErrorsList:
                    tmp = r.error[errorType]
                    r.init_error_data()
                    r.error[errorType] = tmp
                    r.soft_reset()
                    continue
        if iter % 9 == 0:
            profit = calculate_profit(['EthereumClassic', 'Ethereum'])
        miningData += f'PROFIT ETC: {profit["EthereumClassic"]["profitPerMonth"]:.3f}etc,' \
                      f' {profit["EthereumClassic"]["USDPerMonth"]:.2f}$\n'
        miningData += f'PROFIT ETH: {profit["Ethereum"]["profitPerMonth"]:.3f}eth, ' \
                      f'{profit["Ethereum"]["USDPerMonth"]:.2f}$\n'
        miningData += f'HashRate: {farmHashrate}'
        print(miningData)
        with open('./status/index.html', 'w') as outfile:
            outfile.write(miningData.replace('\n', '<br>'))
        print('Sleeping...', iter)
        time.sleep(3)
        iter += 1
