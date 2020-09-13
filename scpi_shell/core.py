# coding=utf8

import cmd
import inspect
import signal
import sys
from pprint import pprint
from socketserver import TCPServer, BaseRequestHandler
from ast import literal_eval
from typing import Callable

import vxi11  # pip install -U python-vxi11
from serial import Serial, SerialException

S_VXI11 = 'vxi11'
S_SERIAL = 'serial'
# PROMPT_LEFT_ARROW = '←'
PROMPT_LEFT_ARROW = '<-'

Vxi11Exception = vxi11.vxi11.Vxi11Exception


class EmptyTimeout(Exception):
    pass


def win32_ctrl_c():
    if sys.platform == 'win32':
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # %ERRORLEVEL% = '-1073741510'


class LinkWrapper:
    def __init__(self, link):
        self.__dict__['_link'] = self._link = link

    @property
    def members(self):
        return {k: v.__doc__ if isinstance(v, Callable) else v for k, v in inspect.getmembers(self._link) if
                k[:2] + k[-2:] != '____' and not isinstance(v, Callable) or k in ('__class__',)}

    def __setattr__(self, key, value):
        setattr(self._link, key, value)

    def __getattr__(self, key):
        return getattr(self._link, key)


class SerialLinkWrapper(LinkWrapper):
    def __init__(self, serial: Serial):
        super(SerialLinkWrapper, self).__init__(serial)

    def read(self):
        d = self._link.read_until().decode()
        if d:
            return d
        else:
            raise EmptyTimeout

    def write(self, s: str):
        self._link.read_all()
        self._link.write(f'{s}\n'.encode())

    def ask(self, s: str):
        self.write(s)
        return self.read()

    def __str__(self):
        return f'{self._link.port}: {self._link}'


class VXI11LinkWrapper(LinkWrapper):
    def __init__(self, inst: vxi11.Instrument):
        super(VXI11LinkWrapper, self).__init__(inst)
        self.ask = inst.ask
        self.read = inst.read
        self.write = inst.write

    def __str__(self):
        return f'{self._link.host}: {self._link}'


class SCPIShell(cmd.Cmd):
    default_conn_type = 'VXI-11'
    default_timeout = 5

    def __init__(self, address: str = None, conn_type: str = None, timeout: float = None):
        self.address = address
        self.conn_type = conn_type or self.default_conn_type
        self.timeout = timeout or self.default_timeout
        self.link = None
        self.ask = None
        self.read = None
        self.write = None
        self.lastcmd_return = None
        self.connected = False
        self.verbose = 0
        super(SCPIShell, self).__init__()
        if self.address:
            self.connect(address, conn_type, timeout)

    def do_verbose(self, line):
        self.verbose = int(line)

    def postcmd(self, stop, line):
        self.lastcmd_return = stop
        return None

    def default(self, line):
        return self.do_scpi(line)

    def onecmd(self, line) -> str:
        ok = False
        try:
            r = super(SCPIShell, self).onecmd(line)
            ok = True
        except Vxi11Exception as e:
            r = f'VXI11 Error: {e.msg}'
        except SerialException as e:
            r = f'Serial Error: {e}'
        except AttributeError as e:
            r = f'Attribute Error: {str(e)}'
        except EmptyTimeout:
            r = f"No return until timeout: '{line}'"
        if ok:
            return r
        else:
            print(r)

    def preloop(self):
        super(SCPIShell, self).preloop()
        self.do_help('')
        if not self.connected:
            address = input('Connect to: ')
            conn_type_list = ('VXI-11', 'Serial')
            conn_type_default = conn_type_list[0]
            conn_type_choose_str_list = []
            for i in range(len(conn_type_list)):
                conn_type_choose_str_list.append(f'{i + 1}={conn_type_list[i]}')
            conn_type_choose_str_list.append(f'default={conn_type_default}')
            choose = input(
                f'Connection Type ({", ".join(conn_type_choose_str_list)}): '
            ).strip()
            if choose == '':
                conn_type = conn_type_default
            else:
                conn_type = conn_type_list[int(choose) - 1]
            timeout = input('Connection timeout in seconds (default=10): ').strip()
            if timeout == '':
                timeout = 10
            elif timeout in ('none', 'None'):
                timeout = None
            else:
                timeout = float(timeout)
            print(self.connect(address, conn_type, timeout))
        self.prompt = f'{self.conn_type}@{self.address} {PROMPT_LEFT_ARROW} '
        for c in ['idn', 'remote']:
            self.onecmd(c)

    def do_scpi(self, line=None):
        """Send (SCPI) command."""
        command = line or input('Send command：')
        if self.verbose:
            print(f'{self.prompt}`{command}`')
        r = self.send_scpi(command)
        if r:
            print(r)
        return r

    def send_scpi(self, command):
        if '?' in command:
            return self.ask(command)
        else:
            self.write(command)

    def link_config(self, key=None, value=None):
        if key is None:
            return self.link
        if value is None:
            return getattr(self.link, key)
        else:
            setattr(self.link, key, value)

    def do_link_config(self, line):
        """get or set attribution of underlying link:
        attr <key_name>
        attr <key_name> <new_value>
        """
        args = line.split(maxsplit=1)
        if not args:
            print(self.link_config())
            pprint(self.link_config('members'))
        elif len(args) == 1:
            key = args[0]
            value = self.link_config(key)
            if key == 'members':
                pprint(value)
            else:
                print(value)
        else:
            self.link_config(args[0], literal_eval(args[-1]))

    def connect(self, address=None, conn_type=None, timeout=None):
        self.address = address = address or self.address
        self.conn_type = conn_type = conn_type or self.conn_type
        timeout = timeout or self.timeout
        timeout = float(timeout)
        self.timeout = timeout
        conn_type_lower = conn_type.lower()
        if conn_type_lower.startswith('vxi'):
            inst = vxi11.Instrument(address)
            inst.timeout = timeout
            self.link = VXI11LinkWrapper(inst)
            self.ask = self.link.ask
            self.write = self.link.write
            self.read = self.link.read
            self.connected = True
        elif conn_type_lower.startswith(S_SERIAL):
            if address.count(':'):
                port, setting = address.split(':', maxsplit=1)
                if setting.count(','):
                    baud, bits = setting.split(',', maxsplit=1)
                    data_bits, parity_bit, stop_bits = bits
                    com = Serial(port=port, baudrate=int(baud), bytesize=int(data_bits), parity=parity_bit.upper(),
                                 stopbits=int(stop_bits))
                else:
                    com = Serial(port=port, baudrate=int(setting))
            else:
                com = Serial(address)
            com.timeout = timeout
            self.link = SerialLinkWrapper(com)
            self.ask = self.link.ask
            self.write = self.link.write
            self.read = self.link.read
            self.connected = True
        else:
            raise NotImplementedError(conn_type)
        return str(self.link)

    def do_connect(self, line=None):
        """Set link to remote:
        connect <address>
        connect <address> <connection_type>
        connect <address> <connection_type> <timeout>
        """
        if not line:
            address, conn_type, timeout = None, None, None
        else:
            args = line.split()
            while len(args) < 3:
                args.append(None)
            address, conn_type, timeout = args
        print(self.connect(address, conn_type, timeout))

    def do_disconnect(self, *noargs):
        """close current underlying link"""
        self.link.close()

    def do_tcprelay(self, line: str):
        """Usage: tcpserver [ADDRESS]:PORT
        Start a TCP socket server as a command repeater, listing on [ADDRESS]:PORT.
        `ADDRESS`, if omitted, default to `localhost`.
        """
        try:
            host, port = line.split(':', maxsplit=1)
            host = host or 'localhost'
            port = int(port)
            self.tcprelay(host, port)
        except ValueError:
            print('Invalid server address: {}'.format(line))
            print('Usage: {}'.format(self.do_tcprelay.__doc__))

    def tcprelay(self, host: str, port: int):
        callback = self.onecmd
        welcome = f'vxi11cmd server, listen on {host}:{port}, connect to {self.address}.\n\n'.encode()

        class CmdServerHandler(BaseRequestHandler):
            def handle(self):
                self.request.send(welcome)
                buffer = bytearray()
                while True:
                    buffer.extend(self.request.recv(64))
                    while True:
                        i = buffer.find(b'\n')
                        if i == -1:
                            break
                        line = bytes(buffer[:i + 1])
                        buffer[:] = buffer[i + 1:]
                        command = line.decode().strip()
                        print(command)
                        answer = callback(command)
                        if answer:
                            self.request.send(answer.encode() + b'\n')

        server = TCPServer((host, port), CmdServerHandler)
        server.serve_forever()

    @staticmethod
    def do_quit(*args):
        """Quit interactive CLI."""
        sys.exit(0)

    def do_local(self, *args):
        """Switch instrument into local mode."""
        return self.do_scpi(':communicate:remote 0')

    def do_remote(self, *args):
        """Switch instrument into remote mode."""
        return self.do_scpi(':communicate:remote 1')

    def do_idn(self, *args):
        """Instrument identity."""
        return self.do_scpi('*idn?')