"""
Grava a tela como MP4 enquanto voce navega livremente no dashboard.
Pressione Ctrl+C no PowerShell para parar a gravacao a qualquer momento.
"""
import time, os, sys
import numpy as np
import pyautogui
import cv2

SAIDA   = r"C:\Users\kelly\OneDrive\Documentos\Claude\twygo-agente-reimplantacao\demo_dashboard.mp4"
FPS     = 12
LARGURA = 1280
ALTURA  = 720

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = cv2.VideoWriter(SAIDA, fourcc, FPS, (LARGURA, ALTURA))

print("=" * 55)
print("  GRAVADOR DE TELA — demo_dashboard.mp4")
print("=" * 55)
print("\n  Voce tem 8 segundos para abrir o dashboard.")
print("  Depois navegue a vontade — clique, selecione,")
print("  troque de aba como quiser.\n")
print("  Para PARAR: pressione Ctrl+C nesta janela.\n")

for i in range(8, 0, -1):
    print(f"  Iniciando em {i}...", end="\r", flush=True)
    time.sleep(1)

print("\n  >>> GRAVANDO <<<  (Ctrl+C para parar)\n")

frames   = 0
intervalo = 1.0 / FPS

try:
    while True:
        t0  = time.time()
        img = pyautogui.screenshot()
        img = img.resize((LARGURA, ALTURA))
        bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        writer.write(bgr)
        frames += 1

        seg = frames // FPS
        print(f"  {seg // 60:02d}:{seg % 60:02d} gravados", end="\r", flush=True)

        elapsed = time.time() - t0
        if elapsed < intervalo:
            time.sleep(intervalo - elapsed)

except KeyboardInterrupt:
    pass

writer.release()

seg   = frames // FPS
mb    = os.path.getsize(SAIDA) / (1024 * 1024) if os.path.exists(SAIDA) else 0
print(f"\n\n  Gravacao encerrada: {seg // 60:02d}:{seg % 60:02d} ({mb:.1f} MB)")
print(f"  Arquivo: {SAIDA}")
print("\n  Para inserir no PowerPoint:")
print("  Slide 6 > Inserir > Video > Este Dispositivo > demo_dashboard.mp4")
print("  Marque 'Iniciar Automaticamente' nas opcoes de reproducao.")
