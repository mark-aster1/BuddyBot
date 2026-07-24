# BuddyBot
An autonomous modular Robot Companion Platform.

# Descriere
BuddyBot este mini asistentul tau modular conceput în jurul unei singure idei centrale: adaptabilitatea reală la nevoile utilizatorului. În loc să fie un robot cu o singură funcție fixă, BuddyBot oferă o platformă universală pe care utilizatorul o poate reconfigura în funcție de context, fără a fi nevoie de un robot separat pentru fiecare sarcină.

# Tehnologii
BuddyBot rulează pe o arhitectură distribuită: un Raspberry Pi 3B+ acționează ca unitate centrală, coordonând tracking vizual, agregare BLE, control motoare și interfața de display, în timp ce patru module ESP32-C3 gestionează sarcini locale (scanere BLE, servomotoare braț, senzor de greutate coș), comunicând cu Raspberry Pi prin USB serial.
Propulsie: configurație tank drive cu 4 motoare GoBilda Yellow Jacket, controlate prin 2 drivere H-Bridge BTS7960 (43A), comandate prin PWM via modul PCA9685 pe I2C.
Urmărire dual-modală: camera Logitech C922 rulează detecție de persoană prin OpenCV cu un model MobileNet SSD, oferind urmărire vizuală principală cu comenzi de mișcare proporționale cu poziția utilizatorului în cadru. Când utilizatorul iese din câmpul vizual, sistemul trece automat pe triangulare BLE: două module ESP32-C3 scanează puterea semnalului (RSSI) unui beacon purtat de utilizator, iar diferența stânga-dreapta determină direcția de rotație a robotului.
## Module interschimbabile:

Braț robotic cu 5 axe (servo-uri Axon MAX, Plex Torque, Axon MINI) și claw interschimbabil, alimentat printr-un modul dedicat de putere pentru servo-uri.
Coș de cumpărături cu load cell 20kg + convertor HX711 pentru cântărire de precizie, plus scanare de coduri de bare direct din fluxul video.
Suport pentru camera Insta360, pentru filmare stabilizată.

Interfață utilizator: display TFT SPI 2.8" cu meniu ierarhic (status sistem, mod urmărire, radar BLE, scanner, testare motoare), navigabil prin gamepad PS5 conectat wireless, cu stream video oglindit și accesibil pe rețea.
Alimentare: baterie principală LiPo 3S dedicată platformei, separată de o a doua baterie pentru modulele consumatoare de energie, prevenind resetări ale sistemului central cauzate de fluctuații de tensiune.

# Cerinte sistem
# BuddyBot – Cerințe Sistem

#### Hardware minim necesar
* Unitate centrală: Raspberry Pi 3B+ sau superior, procesor Cortex-A53 1.4GHz quad-core, minim 1GB RAM.
* Stocare: card microSD, minim 16GB, clasă de viteză 10.
* Sistem de operare: Raspberry Pi OS Lite, fără interfață grafică desktop.
* Cameră: webcam USB compatibilă UVC, de exemplu Logitech C922, rezoluție minim 640x480.
* Microcontrollere: 4 module ESP32-C3 Super Mini, plus un ESP32 folosit ca beacon purtat de utilizator.
* Motoare: 4 motoare DC cu encoder, de exemplu GoBilda Yellow Jacket 312 RPM.
* Drivere motoare: 2 module BTS7960 sau echivalent H-Bridge, minim 20A per canal.
* Controller PWM: modul PCA9685, interfață I2C.
* Servomotoare braț: compatibile cu protocol PWM standard sau serial, de exemplu Axon MAX, Axon MINI, Plex Torque.
* Senzor greutate: load cell maxim 20kg, plus convertor ADC HX711.
* LIDAR: modul LIDAR 2D rotativ, interfață serial sau USB.
* Display: TFT SPI 5.1 inch, driver ILI9341, rezoluție 240x320px.
* Control manual: gamepad PS5 DualSense, plus adaptor Bluetooth USB extern recomandat pentru latență redusă.
* Alimentare: baterie LiPo 3S 11.1V minim 2200mAh pentru platformă, plus baterie secundară 12V minim 3000mAh pentru module.
* Siguranță electrică: breaker sau siguranță 50A pe linia principală, plus siguranțe individuale pentru fiecare subsistem.

#### Cerințe software
* Raspberry Pi OS Lite, versiune Bullseye sau ulterioară.
* Python 3.9 sau mai nou, cu bibliotecile OpenCV, NumPy, Pillow, spidev, pyzbar și evdev.
* Model pre-antrenat MobileNet SSD, format Caffe, pentru detecția persoanei.
* Firmware Arduino C++ pentru ESP32-C3, dezvoltat în Arduino IDE sau PlatformIO.
* Server local, Node.js sau Flask/FastAPI, pentru interfața web și streaming video MJPEG.
* Acces la rețea Wi-Fi locală, Raspberry Pi configurat ca punct de acces propriu.
  
#### Cerințe de mediu și operare
* Spațiu suficient pentru manevrare, rotația pe loc necesitând minim aproximativ 50 pe 50 centimetri liberi.
* Iluminare adecvată pentru detecția vizuală, performanța scăzând considerabil în condiții de lumină foarte slabă.
* Temperatură de operare recomandată între 0 și 40 de grade Celsius, limitare impusă de componentele electronice și de bateriile LiPo.
* Suprafață relativ plană, necesară pentru propulsia de tip tank drive.
* Distanță utilă pentru triangularea BLE, recomandat sub 10-15 metri față de beacon, în funcție de interferențe.

#### Cerințe de utilizator
* Un dispozitiv, telefon sau laptop, conectat la rețeaua Wi-Fi a robotului, pentru acces la interfața web, opțional întrucât display-ul TFT oferă control complet on-board.
* Gamepad PS5 DualSense încărcat și asociat prin Bluetooth, pentru control manual.
* Beacon ESP32 purtat de utilizator, pornit și funcțional, necesar pentru recuperarea urmăririi în cazul pierderii vizuale.


## Realizatori
Mark Aster
Scoala: Liceul Teoretic “Nikolaus Lenau”
Clasa: 11
Judet: Timiș
Oras: Timisoara
Jannik Welzeck
Scoala: Liceul teoretic Nikolaus Lenau
Clasa: 11
Judet: Timiș
Oras: Timisoara
