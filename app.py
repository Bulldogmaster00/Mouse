#!/usr/bin/env python3
import evdev
from evdev import ecodes, InputDevice, UInput
import threading
import time
import subprocess
import os
import signal
import sys
import select
import socket
import json
import struct

class MacHIDController:
    """Controla o Raspberry Pi como dispositivo HID para Mac"""
    
    def __init__(self):
        self.keyboard_device = None
        self.mouse_device = None
        self.running = False
        
        # Dispositivos virtuais para enviar para o Mac
        self.virtual_keyboard = None
        self.virtual_mouse = None
        
        # Estado do HID
        self.modifier_keys = 0x00
        self.keyboard_keys = [0x00] * 6
        self.mouse_buttons = 0x00
        
        # Socket para comunicação com Mac
        self.socket = None
        self.client_socket = None
        
        # Mapeamento de teclas HID
        self.key_map = {
            # Letras
            ecodes.KEY_A: 0x04, ecodes.KEY_B: 0x05, ecodes.KEY_C: 0x06,
            ecodes.KEY_D: 0x07, ecodes.KEY_E: 0x08, ecodes.KEY_F: 0x09,
            ecodes.KEY_G: 0x0A, ecodes.KEY_H: 0x0B, ecodes.KEY_I: 0x0C,
            ecodes.KEY_J: 0x0D, ecodes.KEY_K: 0x0E, ecodes.KEY_L: 0x0F,
            ecodes.KEY_M: 0x10, ecodes.KEY_N: 0x11, ecodes.KEY_O: 0x12,
            ecodes.KEY_P: 0x13, ecodes.KEY_Q: 0x14, ecodes.KEY_R: 0x15,
            ecodes.KEY_S: 0x16, ecodes.KEY_T: 0x17, ecodes.KEY_U: 0x18,
            ecodes.KEY_V: 0x19, ecodes.KEY_W: 0x1A, ecodes.KEY_X: 0x1B,
            ecodes.KEY_Y: 0x1C, ecodes.KEY_Z: 0x1D,
            
            # Números
            ecodes.KEY_1: 0x1E, ecodes.KEY_2: 0x1F, ecodes.KEY_3: 0x20,
            ecodes.KEY_4: 0x21, ecodes.KEY_5: 0x22, ecodes.KEY_6: 0x23,
            ecodes.KEY_7: 0x24, ecodes.KEY_8: 0x25, ecodes.KEY_9: 0x26,
            ecodes.KEY_0: 0x27,
            
            # Teclas especiais
            ecodes.KEY_ENTER: 0x28, ecodes.KEY_ESC: 0x29,
            ecodes.KEY_BACKSPACE: 0x2A, ecodes.KEY_TAB: 0x2B,
            ecodes.KEY_SPACE: 0x2C, ecodes.KEY_MINUS: 0x2D,
            ecodes.KEY_EQUAL: 0x2E, ecodes.KEY_LEFTBRACE: 0x2F,
            ecodes.KEY_RIGHTBRACE: 0x30, ecodes.KEY_BACKSLASH: 0x31,
            ecodes.KEY_SEMICOLON: 0x33, ecodes.KEY_APOSTROPHE: 0x34,
            ecodes.KEY_GRAVE: 0x35, ecodes.KEY_COMMA: 0x36,
            ecodes.KEY_DOT: 0x37, ecodes.KEY_SLASH: 0x38,
            ecodes.KEY_CAPSLOCK: 0x39,
            
            # Teclas de função
            ecodes.KEY_F1: 0x3A, ecodes.KEY_F2: 0x3B,
            ecodes.KEY_F3: 0x3C, ecodes.KEY_F4: 0x3D,
            ecodes.KEY_F5: 0x3E, ecodes.KEY_F6: 0x3F,
            ecodes.KEY_F7: 0x40, ecodes.KEY_F8: 0x41,
            ecodes.KEY_F9: 0x42, ecodes.KEY_F10: 0x43,
            ecodes.KEY_F11: 0x44, ecodes.KEY_F12: 0x45,
            
            # Setas
            ecodes.KEY_RIGHT: 0x4F, ecodes.KEY_LEFT: 0x50,
            ecodes.KEY_DOWN: 0x51, ecodes.KEY_UP: 0x52,
        }
        
        # Modifier keys
        self.modifier_map = {
            ecodes.KEY_LEFTSHIFT: 0x02,
            ecodes.KEY_RIGHTSHIFT: 0x20,
            ecodes.KEY_LEFTCTRL: 0x01,
            ecodes.KEY_RIGHTCTRL: 0x10,
            ecodes.KEY_LEFTALT: 0x04,    # Option no Mac
            ecodes.KEY_RIGHTALT: 0x40,
            ecodes.KEY_LEFTMETA: 0x08,   # Command no Mac
            ecodes.KEY_RIGHTMETA: 0x80,
        }
        
        # Inverte o mapeamento para uso posterior
        self.hid_to_evdev = {v: k for k, v in self.key_map.items()}
        self.modifier_to_evdev = {v: k for k, v in self.modifier_map.items()}
    
    def setup_bluetooth_simple(self):
        """Configuração simples do Bluetooth para pareamento"""
        print("🔧 Configurando Bluetooth...")
        
        try:
            # Parar serviços que podem interferir
            subprocess.run(["sudo", "systemctl", "stop", "bluetooth"], check=False)
            time.sleep(1)
            
            # Ativar interface Bluetooth
            subprocess.run(["sudo", "hciconfig", "hci0", "up"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "piscan"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "name", "Raspberry Pi Remote"], check=False)
            
            # Obter endereço MAC
            result = subprocess.run(["hciconfig", "hci0"], capture_output=True, text=True)
            mac_address = "Desconhecido"
            for line in result.stdout.split('\n'):
                if 'BD Address' in line:
                    mac_address = line.split()[-1]
                    break
            
            print(f"📡 Bluetooth ativado: {mac_address}")
            print(f"📛 Nome: Raspberry Pi Remote")
            
            # Iniciar agente Bluetooth para pareamento
            print("🤝 Agente de pareamento iniciado (pincode: 0000)")
            self.start_bluetooth_agent()
            
            return True
            
        except Exception as e:
            print(f"❌ Erro na configuração Bluetooth: {e}")
            return False
    
    def start_bluetooth_agent(self):
        """Inicia agente Bluetooth para pareamento"""
        agent_script = '''
#!/usr/bin/python3
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import sys

class Agent(dbus.service.Object):
    def __init__(self, bus, path):
        super().__init__(bus, path)
    
    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        print("Agent released")
    
    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        print(f"AuthorizeService: {device}, {uuid}")
        return
    
    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        print(f"RequestPinCode: {device}")
        return "0000"
    
    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        print(f"RequestConfirmation: {device}, {passkey}")
        return
    
    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        print(f"RequestAuthorization: {device}")
        return
    
    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="u")
    def Capabilities(self, device, capability):
        print(f"Capabilities: {device}, {capability}")
        return 1

if __name__ == "__main__":
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    
    # Registrar agente
    agent = Agent(bus, "/test/agent")
    obj = bus.get_object("org.bluez", "/org/bluez")
    manager = dbus.Interface(obj, "org.bluez.AgentManager1")
    manager.RegisterAgent("/test/agent", "DisplayYesNo")
    manager.RequestDefaultAgent("/test/agent")
    
    print("Agent registered successfully")
    
    # Manter o agente ativo
    loop = GLib.MainLoop()
    loop.run()
'''
        
        # Salvar e executar agente em background
        with open('/tmp/bluetooth_agent.py', 'w') as f:
            f.write(agent_script)
        
        # Dar permissão e executar
        subprocess.Popen(['python3', '/tmp/bluetooth_agent.py'], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL)
        time.sleep(2)
    
    def setup_tcp_server(self):
        """Configura servidor TCP para comunicação com Mac"""
        print("🌐 Configurando servidor TCP...")
        
        try:
            # Criar socket TCP
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Vincular à porta 12345
            self.socket.bind(('0.0.0.0', 12345))
            self.socket.listen(1)
            
            print("✅ Servidor TCP configurado na porta 12345")
            print("📡 Aguardando conexão do Mac...")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao configurar servidor TCP: {e}")
            return False
    
    def wait_for_connection(self):
        """Aguarda conexão do Mac"""
        print("\n" + "=" * 60)
        print("🖥️  AGUARDANDO CONEXÃO DO MAC")
        print("=" * 60)
        
        try:
            # Aceitar conexão
            self.client_socket, client_address = self.socket.accept()
            print(f"✅ Conectado ao Mac: {client_address}")
            
            # Enviar mensagem de confirmação
            self.send_to_mac({"type": "connected", "message": "Raspberry Pi Remote Ready"})
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao aguardar conexão: {e}")
            return False
    
    def send_to_mac(self, data):
        """Envia dados para o Mac via socket"""
        if not self.client_socket:
            return False
        
        try:
            # Converter para JSON
            json_data = json.dumps(data).encode('utf-8')
            
            # Enviar tamanho primeiro
            size = struct.pack('I', len(json_data))
            self.client_socket.send(size)
            
            # Enviar dados
            self.client_socket.send(json_data)
            return True
            
        except Exception as e:
            print(f"⚠️ Erro ao enviar para Mac: {e}")
            return False
    
    def create_virtual_devices(self):
        """Cria dispositivos virtuais para capturar entrada"""
        print("🖥️ Criando dispositivos virtuais...")
        
        try:
            # Capabilities para teclado virtual
            keyboard_cap = {
                ecodes.EV_KEY: list(self.key_map.keys()) + list(self.modifier_map.keys())
            }
            
            # Capabilities para mouse virtual
            mouse_cap = {
                ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE],
                ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL]
            }
            
            # Criar dispositivos virtuais
            self.virtual_keyboard = UInput(keyboard_cap, name='Virtual Raspberry Pi Keyboard', 
                                          bustype=ecodes.BUS_USB, vendor=0x1, product=0x1)
            
            self.virtual_mouse = UInput(mouse_cap, name='Virtual Raspberry Pi Mouse', 
                                       bustype=ecodes.BUS_USB, vendor=0x1, product=0x2)
            
            print("✅ Dispositivos virtuais criados")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao criar dispositivos virtuais: {e}")
            return False
    
    def find_input_devices(self):
        """Encontra dispositivos de entrada (teclado/mouse)"""
        try:
            devices = [InputDevice(path) for path in evdev.list_devices()]
            
            print("\n🔍 Procurando dispositivos de entrada...")
            for i, device in enumerate(devices):
                print(f"   {i}: {device.name} [{device.path}]")
                
                # Detecção automática
                if not self.keyboard_device and ('keyboard' in device.name.lower() or 'kbd' in device.name.lower()):
                    self.keyboard_device = device
                    print(f"     ✅ Teclado detectado")
                    
                if not self.mouse_device and ('mouse' in device.name.lower()):
                    self.mouse_device = device
                    print(f"     ✅ Mouse detectado")
            
            return devices
            
        except Exception as e:
            print(f"❌ Erro ao encontrar dispositivos: {e}")
            return []
    
    def select_input_devices(self, devices):
        """Permite seleção manual dos dispositivos"""
        print("\n🎯 Selecione os dispositivos manualmente:")
        
        try:
            print("\nTeclados disponíveis:")
            keyboards = [d for d in devices if 'key' in d.name.lower() or any(x in d.name.lower() for x in ['kbd', 'keyboard'])]
            for i, dev in enumerate(keyboards):
                print(f"  {i}: {dev.name}")
            
            if keyboards:
                kb_choice = int(input("Número do teclado: "))
                self.keyboard_device = keyboards[kb_choice]
            
            print("\nMouses disponíveis:")
            mouses = [d for d in devices if 'mouse' in d.name.lower()]
            for i, dev in enumerate(mouses):
                print(f"  {i}: {dev.name}")
            
            if mouses:
                mouse_choice = int(input("Número do mouse: "))
                self.mouse_device = mouses[mouse_choice]
            
            return True
            
        except (ValueError, IndexError) as e:
            print(f"❌ Seleção inválida: {e}")
            return False
    
    def grab_devices(self):
        """Captura dispositivos para evitar entrada local"""
        try:
            if self.keyboard_device:
                self.keyboard_device.grab()
                print(f"🔒 Teclado capturado: {self.keyboard_device.name}")
            
            if self.mouse_device:
                self.mouse_device.grab()
                print(f"🔒 Mouse capturado: {self.mouse_device.name}")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao capturar dispositivos: {e}")
            return False
    
    def process_keyboard_event(self, event):
        """Processa eventos do teclado e envia para o Mac"""
        if event.type == ecodes.EV_KEY:
            scancode = event.code
            pressed = event.value == 1
            
            # Enviar evento para o Mac
            self.send_to_mac({
                "type": "keyboard",
                "code": int(scancode),
                "pressed": pressed,
                "key_name": ecodes.KEY[scancode] if scancode in ecodes.KEY else str(scancode)
            })
            
            # Simular no dispositivo virtual local (opcional)
            if self.virtual_keyboard:
                try:
                    self.virtual_keyboard.write(ecodes.EV_KEY, scancode, 1 if pressed else 0)
                    self.virtual_keyboard.syn()
                except:
                    pass
    
    def process_mouse_event(self, event):
        """Processa eventos do mouse e envia para o Mac"""
        if event.type == ecodes.EV_REL:
            # Movimento do mouse
            axis = 'x' if event.code == ecodes.REL_X else 'y' if event.code == ecodes.REL_Y else 'wheel'
            
            self.send_to_mac({
                "type": "mouse_move",
                "axis": axis,
                "value": event.value
            })
            
            # Simular no dispositivo virtual local
            if self.virtual_mouse:
                try:
                    self.virtual_mouse.write(ecodes.EV_REL, event.code, event.value)
                    self.virtual_mouse.syn()
                except:
                    pass
                
        elif event.type == ecodes.EV_KEY:
            # Botões do mouse
            button_map = {
                ecodes.BTN_LEFT: "left",
                ecodes.BTN_RIGHT: "right",
                ecodes.BTN_MIDDLE: "middle"
            }
            
            if event.code in button_map:
                self.send_to_mac({
                    "type": "mouse_button",
                    "button": button_map[event.code],
                    "pressed": event.value == 1
                })
                
                # Simular no dispositivo virtual local
                if self.virtual_mouse:
                    try:
                        self.virtual_mouse.write(ecodes.EV_KEY, event.code, 1 if event.value == 1 else 0)
                        self.virtual_mouse.syn()
                    except:
                        pass
    
    def keyboard_listener(self):
        """Escuta eventos do teclado"""
        if not self.keyboard_device:
            print("⚠️ Nenhum teclado disponível para escuta")
            return
        
        print(f"🎹 Ouvindo teclado: {self.keyboard_device.name}")
        
        try:
            for event in self.keyboard_device.read_loop():
                if not self.running:
                    break
                self.process_keyboard_event(event)
        except Exception as e:
            print(f"⚠️ Erro no listener do teclado: {e}")
    
    def mouse_listener(self):
        """Escuta eventos do mouse"""
        if not self.mouse_device:
            print("⚠️ Nenhum mouse disponível para escuta")
            return
        
        print(f"🖱️ Ouvindo mouse: {self.mouse_device.name}")
        
        try:
            for event in self.mouse_device.read_loop():
                if not self.running:
                    break
                self.process_mouse_event(event)
        except Exception as e:
            print(f"⚠️ Erro no listener do mouse: {e}")
    
    def connection_monitor(self):
        """Monitora a conexão com o Mac"""
        while self.running:
            try:
                # Testar conexão
                if self.client_socket:
                    # Tentar enviar ping
                    self.send_to_mac({"type": "ping", "time": time.time()})
                    
                    # Verificar se socket ainda está válido
                    ready = select.select([self.client_socket], [], [], 0.5)
                    if ready[0]:
                        # Tentar ler dados (deve falhar se desconectado)
                        try:
                            data = self.client_socket.recv(1, socket.MSG_PEEK)
                            if data == b'':
                                raise ConnectionError("Connection closed")
                        except:
                            print("❌ Conexão com Mac perdida")
                            self.client_socket = None
                            break
                
                time.sleep(1)
                
            except Exception as e:
                print(f"⚠️ Erro no monitor de conexão: {e}")
                self.client_socket = None
                break
    
    def start(self):
        """Inicia o controle remoto"""
        print("=" * 60)
        print("🖥️  RASPBERRY PI → MAC REMOTE CONTROL")
        print("=" * 60)
        
        # Passo 1: Configurar Bluetooth
        if not self.setup_bluetooth_simple():
            print("⚠️ Bluetooth não configurado - usando apenas TCP")
        
        # Passo 2: Configurar servidor TCP
        if not self.setup_tcp_server():
            print("❌ Falha na configuração do servidor TCP")
            return
        
        # Passo 3: Criar dispositivos virtuais
        self.create_virtual_devices()
        
        # Passo 4: Encontrar dispositivos de entrada
        devices = self.find_input_devices()
        
        if not devices:
            print("❌ Nenhum dispositivo de entrada encontrado")
            return
        
        # Passo 5: Verificar/Selecionar dispositivos
        if not (self.keyboard_device and self.mouse_device):
            if not self.select_input_devices(devices):
                print("❌ Dispositivos não selecionados")
                return
        
        print(f"\n✅ Dispositivos selecionados:")
        print(f"   Teclado: {self.keyboard_device.name}")
        print(f"   Mouse: {self.mouse_device.name}")
        
        # Passo 6: Capturar dispositivos
        if not self.grab_devices():
            print("⚠️  Dispositivos não capturados - entrada local ainda funcionará")
        
        # Passo 7: Aguardar conexão do Mac
        print("\n" + "=" * 60)
        print("📡 AGUARDANDO CONEXÃO DO MAC")
        print("=" * 60)
        print("\n💡 No seu Mac, execute:")
        print("   python3 mac_client.py --host IP_DO_RASPBERRY_PI")
        print("\n   Para descobrir o IP do Raspberry Pi:")
        print("   hostname -I")
        
        if not self.wait_for_connection():
            print("❌ Falha na conexão")
            return
        
        # Passo 8: Iniciar threads
        try:
            self.running = True
            
            print("\n" + "=" * 60)
            print("✅ CONEXÃO ESTABELECIDA!")
            print("=" * 60)
            print("\n🎮 Controle remoto ativo!")
            print("   Todos os movimentos do teclado e mouse serão enviados para o Mac")
            print("\n🛑 Pressione Ctrl+C para parar")
            
            # Iniciar listeners em threads separadas
            keyboard_thread = threading.Thread(target=self.keyboard_listener, daemon=True)
            mouse_thread = threading.Thread(target=self.mouse_listener, daemon=True)
            monitor_thread = threading.Thread(target=self.connection_monitor, daemon=True)
            
            keyboard_thread.start()
            mouse_thread.start()
            monitor_thread.start()
            
            # Manter thread principal rodando
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Parando controle...")
        finally:
            self.stop()
    
    def stop(self):
        """Para o controle e limpa recursos"""
        print("\n🧹 Limpando recursos...")
        self.running = False
        
        # Liberar dispositivos
        try:
            if self.keyboard_device:
                self.keyboard_device.ungrab()
                print("🔓 Teclado liberado")
            
            if self.mouse_device:
                self.mouse_device.ungrab()
                print("🔓 Mouse liberado")
        except:
            pass
        
        # Fechar sockets
        try:
            if self.client_socket:
                self.client_socket.close()
            if self.socket:
                self.socket.close()
            print("🔌 Conexões fechadas")
        except:
            pass
        
        # Fechar dispositivos virtuais
        try:
            if self.virtual_keyboard:
                self.virtual_keyboard.close()
            if self.virtual_mouse:
                self.virtual_mouse.close()
            print("🖥️  Dispositivos virtuais fechados")
        except:
            pass
        
        print("\n✅ Controle encerrado.")

def main():
    """Função principal"""
    # Verificar se está rodando como root
    if os.geteuid() != 0:
        print("❌ Este programa precisa ser executado como root!")
        print("   Execute com: sudo python3 pi_remote.py")
        sys.exit(1)
    
    # Criar e iniciar controlador
    controller = MacHIDController()
    
    # Configurar handler para Ctrl+C
    def signal_handler(sig, frame):
        print("\n\n🛑 Interrupção recebida")
        controller.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        controller.start()
    except Exception as e:
        print(f"❌ Erro fatal: {e}")
        controller.stop()

if __name__ == "__main__":
    main()
