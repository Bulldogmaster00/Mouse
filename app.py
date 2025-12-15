#!/usr/bin/env python3
import bluetooth
import pyautogui

def main():
    # Configura socket Bluetooth
    server = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    server.bind(("", 4))
    server.listen(1)
    
    print("Aguardando Bluetooth...")
    
    while True:
        client, addr = server.accept()
        print("Conectado")
        
        while True:
            data = client.recv(1024)
            if data:
                # Digita o número
                pyautogui.write("956523332")
                print("Digitado: 956523332")
                client.send(b"digitado_ok")
        
        client.close()

if __name__ == "__main__":
    main()
