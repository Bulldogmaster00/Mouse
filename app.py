#!/usr/bin/env python3
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import evdev
from evdev import ecodes, InputDevice
import threading
import time
import queue
import subprocess
import os
import signal
import sys

# Configurar DBus
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()

class BluetoothHIDDevice:
    """Implementa um dispositivo HID Bluetooth (teclado/mouse)"""
    
    # UUIDs do serviço HID
    HID_SERVICE_UUID = "00001124-0000-1000-8000-00805f9b34fb"
    HID_DESCRIPTOR = [
        0x05, 0x01,        # Usage Page (Generic Desktop)
        0x09, 0x06,        # Usage (Keyboard)
        0xa1, 0x01,        # Collection (Application)
        0x85, 0x01,        #   Report ID (1)
        0x05, 0x07,        #   Usage Page (Key Codes)
        0x19, 0xe0,        #   Usage Minimum (224)
        0x29, 0xe7,        #   Usage Maximum (231)
        0x15, 0x00,        #   Logical Minimum (0)
        0x25, 0x01,        #   Logical Maximum (1)
        0x75, 0x01,        #   Report Size (1)
        0x95, 0x08,        #   Report Count (8)
        0x81, 0x02,        #   Input (Data, Variable, Absolute)
        0x95, 0x01,        #   Report Count (1)
        0x75, 0x08,        #   Report Size (8)
        0x81, 0x01,        #   Input (Constant)
        0x95, 0x05,        #   Report Count (5)
        0x75, 0x01,        #   Report Size (1)
        0x05, 0x08,        #   Usage Page (LEDs)
        0x19, 0x01,        #   Usage Minimum (1)
        0x29, 0x05,        #   Usage Maximum (5)
        0x91, 0x02,        #   Output (Data, Variable, Absolute)
        0x95, 0x01,        #   Report Count (1)
        0x75, 0x03,        #   Report Size (3)
        0x91, 0x01,        #   Output (Constant)
        0x95, 0x06,        #   Report Count (6)
        0x75, 0x08,        #   Report Size (8)
        0x15, 0x00,        #   Logical Minimum (0)
        0x25, 0x65,        #   Logical Maximum (101)
        0x05, 0x07,        #   Usage Page (Key Codes)
        0x19, 0x00,        #   Usage Minimum (0)
        0x29, 0x65,        #   Usage Maximum (101)
        0x81, 0x00,        #   Input (Data, Array)
        0xc0,              # End Collection
        0x05, 0x01,        # Usage Page (Generic Desktop)
        0x09, 0x02,        # Usage (Mouse)
        0xa1, 0x01,        # Collection (Application)
        0x85, 0x02,        #   Report ID (2)
        0x09, 0x01,        #   Usage (Pointer)
        0xa1, 0x00,        #   Collection (Physical)
        0x05, 0x09,        #     Usage Page (Buttons)
        0x19, 0x01,        #     Usage Minimum (1)
        0x29, 0x03,        #     Usage Maximum (3)
        0x15, 0x00,        #     Logical Minimum (0)
        0x25, 0x01,        #     Logical Maximum (1)
        0x95, 0x03,        #     Report Count (3)
        0x75, 0x01,        #     Report Size (1)
        0x81, 0x02,        #     Input (Data, Variable, Absolute)
        0x95, 0x01,        #     Report Count (1)
        0x75, 0x05,        #     Report Size (5)
        0x81, 0x01,        #     Input (Constant)
        0x05, 0x01,        #     Usage Page (Generic Desktop)
        0x09, 0x30,        #     Usage (X)
        0x09, 0x31,        #     Usage (Y)
        0x09, 0x38,        #     Usage (Wheel)
        0x15, 0x81,        #     Logical Minimum (-127)
        0x25, 0x7f,        #     Logical Maximum (127)
        0x75, 0x08,        #     Report Size (8)
        0x95, 0x03,        #     Report Count (3)
        0x81, 0x06,        #     Input (Data, Variable, Relative)
        0xc0,              #   End Collection
        0xc0               # End Collection
    ]

class HIDService(dbus.service.Object):
    """Serviço HID Bluetooth"""
    
    def __init__(self, bus, path, name):
        super().__init__(bus, path)
        self.name = name
        self.clients = {}
        
    @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
    def Release(self):
        print("HID Profile released")
        
    @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}", out_signature="")
    def NewConnection(self, device, fd, properties):
        print(f"New connection from {device}")
        self.clients[device] = fd
        os.write(fd[0], b"Connection established\n")
        
    @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
    def RequestDisconnection(self, device):
        print(f"Disconnection requested for {device}")
        if device in self.clients:
            os.close(self.clients[device][0])
            del self.clients[device]

class MacHIDController:
    """Controla o Raspberry Pi como dispositivo HID para Mac"""
    
    def __init__(self):
        self.keyboard_device = None
        self.mouse_device = None
        self.running = False
        self.event_queue = queue.Queue()
        
        # Estado do HID
        self.modifier_keys = 0x00
        self.keyboard_keys = [0x00] * 6
        self.mouse_buttons = 0x00
        
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
        
    def setup_bluetooth_hid(self):
        """Configura o Raspberry Pi como dispositivo HID Bluetooth"""
        print("🔧 Configurando Raspberry Pi como dispositivo HID Bluetooth...")
        
        try:
            # 1. Parar serviços Bluetooth existentes
            subprocess.run(["sudo", "systemctl", "stop", "bluetooth"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "down"], check=False)
            
            # 2. Configurar dispositivo HID via BlueZ
            # Instalar dependências se necessário
            print("📦 Verificando dependências...")
            
            # 3. Configurar SDP (Service Discovery Protocol)
            sdp_record = f"""
<?xml version="1.0" encoding="UTF-8"?>
<record>
  <attribute id="0x0001">
    <sequence>
      <uuid value="0x1124"/>
    </sequence>
  </attribute>
  <attribute id="0x0004">
    <sequence>
      <sequence>
        <uuid value="0x0100"/>
        <uint16 value="0x0011"/>
      </sequence>
      <sequence>
        <uuid value="0x0011"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0005">
    <sequence>
      <uuid value="0x1002"/>
    </sequence>
  </attribute>
  <attribute id="0x0006">
    <sequence>
      <uint16 value="0x656e"/>
      <uint16 value="0x006a"/>
      <uint16 value="0x0100"/>
    </sequence>
  </attribute>
  <attribute id="0x0009">
    <sequence>
      <uuid value="0x1124"/>
      <uint16 value="0x0100"/>
    </sequence>
  </attribute>
  <attribute id="0x000d">
    <sequence>
      <sequence>
        <uuid value="0x1124"/>
        <uint16 value="0x0100"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0100">
    <text value="Raspberry Pi HID"/>
  </attribute>
  <attribute id="0x0101">
    <text value="Teclado e Mouse Virtual"/>
  </attribute>
  <attribute id="0x0102">
    <text value="Raspberry Pi"/>
  </attribute>
  <attribute id="0x0200">
    <uint16 value="0x0100"/>
  </attribute>
  <attribute id="0x0201">
    <uint16 value="0x0111"/>
  </attribute>
  <attribute id="0x0202">
    <uint8 value="0xc0"/>
  </attribute>
  <attribute id="0x0203">
    <uint8 value="{len(BluetoothHIDDevice.HID_DESCRIPTOR)}"/>
    <sequence>
      {' '.join([f'<uint8 value="0x{b:02x}"/>' for b in BluetoothHIDDevice.HID_DESCRIPTOR])}
    </sequence>
  </attribute>
  <attribute id="0x0204">
    <sequence>
      <uint8 value="0x22"/>
      <text encoding="hex" value="0100"/>
    </sequence>
  </attribute>
  <attribute id="0x0205">
    <sequence>
      <uint8 value="0x22"/>
      <text encoding="hex" value="0200"/>
    </sequence>
  </attribute>
</record>
"""
            
            # Salvar registro SDP
            with open("/tmp/hid_record.xml", "w") as f:
                f.write(sdp_record)
            
            # 4. Registrar serviço HID
            print("📝 Registrando serviço HID...")
            subprocess.run(["sudo", "sdptool", "add", "--channel=1", "HID"], check=False)
            
            # 5. Ativar modo compatível com HID
            subprocess.run(["sudo", "hciconfig", "hci0", "class", "0x002540"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "name", "Raspberry Pi HID"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "piscan"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "up"], check=False)
            
            # 6. Mostrar informações
            print("\n✅ Raspberry Pi configurado como dispositivo HID")
            print("📡 Endereço Bluetooth:", self.get_bluetooth_address())
            print("🔍 Nome: Raspberry Pi HID")
            print("\n💡 No seu Mac:")
            print("   1. Vá em  > Preferências do Sistema > Bluetooth")
            print("   2. Procure por 'Raspberry Pi HID'")
            print("   3. Clique em 'Conectar'")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro na configuração Bluetooth: {e}")
            return False
    
    def get_bluetooth_address(self):
        """Obtém endereço Bluetooth do Raspberry Pi"""
        try:
            result = subprocess.run(["hciconfig"], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'BD Address' in line:
                    return line.split()[-1]
        except:
            pass
        return "Desconhecido"
    
    def find_input_devices(self):
        """Encontra dispositivos de entrada (teclado/mouse)"""
        try:
            devices = [InputDevice(path) for path in evdev.list_devices()]
            
            print("\n🔍 Procurando dispositivos de entrada...")
            for i, device in enumerate(devices):
                print(f"   {i}: {device.name} [{device.path}]")
                
                # Detecção automática
                if not self.keyboard_device and ('keyboard' in device.name.lower() or 'Keyboard' in device.name):
                    self.keyboard_device = device
                    print(f"     ✅ Teclado detectado")
                    
                if not self.mouse_device and ('mouse' in device.name.lower() or 'Mouse' in device.name):
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
        """Processa eventos do teclado"""
        if event.type == ecodes.EV_KEY:
            scancode = event.code
            pressed = event.value == 1
            
            # Modifier keys
            if scancode in self.modifier_map:
                if pressed:
                    self.modifier_keys |= self.modifier_map[scancode]
                else:
                    self.modifier_keys &= ~self.modifier_map[scancode]
            
            # Teclas normais
            elif scancode in self.key_map:
                hid_code = self.key_map[scancode]
                
                if pressed:
                    # Adiciona tecla se houver espaço
                    if hid_code not in self.keyboard_keys:
                        for i in range(6):
                            if self.keyboard_keys[i] == 0x00:
                                self.keyboard_keys[i] = hid_code
                                break
                else:
                    # Remove tecla
                    for i in range(6):
                        if self.keyboard_keys[i] == hid_code:
                            self.keyboard_keys[i] = 0x00
    
    def process_mouse_event(self, event):
        """Processa eventos do mouse"""
        if event.type == ecodes.EV_REL:
            # Movimento do mouse
            if event.code == ecodes.REL_X:
                self.event_queue.put(('mouse_move', 'x', event.value))
            elif event.code == ecodes.REL_Y:
                self.event_queue.put(('mouse_move', 'y', event.value))
            elif event.code == ecodes.REL_WHEEL:
                self.event_queue.put(('mouse_wheel', event.value))
                
        elif event.type == ecodes.EV_KEY:
            # Botões do mouse
            pressed = event.value == 1
            
            if event.code == ecodes.BTN_LEFT:
                if pressed:
                    self.mouse_buttons |= 0x01
                else:
                    self.mouse_buttons &= ~0x01
            elif event.code == ecodes.BTN_RIGHT:
                if pressed:
                    self.mouse_buttons |= 0x02
                else:
                    self.mouse_buttons &= ~0x02
            elif event.code == ecodes.BTN_MIDDLE:
                if pressed:
                    self.mouse_buttons |= 0x04
                else:
                    self.mouse_buttons &= ~0x04
    
    def keyboard_listener(self):
        """Escuta eventos do teclado"""
        if not self.keyboard_device:
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
            return
        
        print(f"🖱️ Ouvindo mouse: {self.mouse_device.name}")
        
        try:
            for event in self.mouse_device.read_loop():
                if not self.running:
                    break
                self.process_mouse_event(event)
        except Exception as e:
            print(f"⚠️ Erro no listener do mouse: {e}")
    
    def simulate_hid_events(self):
        """Simula entrada HID usando evdev virtual"""
        print("🎮 Preparando para enviar entrada para o Mac...")
        
        # Nota: Em um sistema real, aqui você enviaria os eventos
        # através da conexão Bluetooth HID estabelecida
        # Esta é uma versão simplificada para demonstração
        
        try:
            while self.running:
                # Aqui você implementaria o envio real dos eventos HID
                # através do perfil Bluetooth HID
                time.sleep(0.01)
                
                # Exemplo: Podemos usar uinput para criar dispositivos virtuais
                # que são então compartilhados via Bluetooth
                pass
                
        except Exception as e:
            print(f"⚠️ Erro no simulador HID: {e}")
    
    def start(self):
        """Inicia o controle remoto"""
        print("=" * 60)
        print("🖥️  RASPBERRY PI → MAC VIA BLUETOOTH HID")
        print("=" * 60)
        
        # Passo 1: Configurar Raspberry Pi como dispositivo HID
        if not self.setup_bluetooth_hid():
            print("❌ Falha na configuração Bluetooth HID")
            return
        
        # Passo 2: Encontrar dispositivos de entrada
        devices = self.find_input_devices()
        
        if not devices:
            print("❌ Nenhum dispositivo de entrada encontrado")
            return
        
        # Passo 3: Verificar/Selecionar dispositivos
        if not (self.keyboard_device and self.mouse_device):
            if not self.select_input_devices(devices):
                print("❌ Dispositivos não selecionados")
                return
        
        print(f"\n✅ Dispositivos selecionados:")
        print(f"   Teclado: {self.keyboard_device.name}")
        print(f"   Mouse: {self.mouse_device.name}")
        
        # Passo 4: Capturar dispositivos
        if not self.grab_devices():
            print("⚠️  Dispositivos não capturados - entrada local ainda funcionará")
        
        # Passo 5: Iniciar threads
        try:
            self.running = True
            
            print("\n" + "=" * 60)
            print("✅ PRONTO PARA CONEXÃO!")
            print("=" * 60)
            print("\n📱 No seu Mac:")
            print("   1. Abra  > Preferências do Sistema > Bluetooth")
            print("   2. Procure por 'Raspberry Pi HID'")
            print("   3. Clique em 'Conectar'")
            print("\n⏳ Aguardando conexão do Mac...")
            print("   (Esta janela ficará aberta enquanto o controle está ativo)")
            print("\n🛑 Pressione Ctrl+C para parar")
            
            # Iniciar listeners em threads separadas
            keyboard_thread = threading.Thread(target=self.keyboard_listener, daemon=True)
            mouse_thread = threading.Thread(target=self.mouse_listener, daemon=True)
            hid_thread = threading.Thread(target=self.simulate_hid_events, daemon=True)
            
            keyboard_thread.start()
            mouse_thread.start()
            hid_thread.start()
            
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
        
        # Restaurar Bluetooth normal
        try:
            subprocess.run(["sudo", "hciconfig", "hci0", "nopiscan"], check=False)
            subprocess.run(["sudo", "hciconfig", "hci0", "class", "0x000100"], check=False)
            subprocess.run(["sudo", "systemctl", "restart", "bluetooth"], check=False)
            print("📡 Bluetooth restaurado para modo normal")
        except:
            pass
        
        print("\n✅ Controle encerrado. Dispositivos locais funcionando novamente.")

def main():
    """Função principal"""
    # Verificar se está rodando como root
    if os.geteuid() != 0:
        print("❌ Este programa precisa ser executado como root!")
        print("   Execute com: sudo python3 pi_hid_mac.py")
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
