#!/usr/bin/env python3
import bluetooth
import pyautogui

def main():
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
                pyautogui.click()
                client.send(b"clique_ok")
        
        client.close()

if __name__ == "__main__":
    main()
