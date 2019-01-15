from network_socket import NetworkSocket


eth008 = NetworkSocket()


def connect(ip, port, password):
    return eth008.connect_socket(ip, port, password)


def disconnect():
    eth008.close_socket()


def reboot(relay):
    pulse_time = '\x14' # xC8 - 200ms; x64 - 100ms; x32 - 50ms; x14 - 20ms
    eth008.write('{}{}{}'.format('\x20', chr(int(relay)), pulse_time))
    get_states()


def get_states():
    eth008.write('\x24')          # send command and read back responce byte
    states = eth008.read(1)
    str_states = 'Relay states 8->1 : ' + ''.join('{0:08b}'.format(ord(x), 'b') for x in states)
    print(str_states)
    return str_states

while True:
    response = input(">>")
    connect('92.38.195.170', 17494, 'Password')
    reboot(response)
    disconnect()
