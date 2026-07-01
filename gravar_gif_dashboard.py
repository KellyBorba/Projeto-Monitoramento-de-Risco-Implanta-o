"""
Captura o dashboard Streamlit e gera um GIF animado para a apresentação.
Execute com o navegador aberto em http://localhost:8501 ocupando boa parte da tela.
"""
import time
import pyautogui
import pygetwindow as gw
from PIL import Image
import os

SAIDA = r"C:\Users\kelly\OneDrive\Documentos\Claude\twygo-agente-reimplantacao\demo_dashboard.gif"
FRAMES_POR_ETAPA = 3   # capturas por posição
DELAY_FRAME = 0.6      # segundos entre frames
DELAY_SCROLL = 1.2     # pausa após rolar a página
RESIZE = (1280, 720)   # tamanho final de cada frame

pyautogui.FAILSAFE = True

def capturar_frame(region=None):
    img = pyautogui.screenshot(region=region)
    return img.resize(RESIZE, Image.LANCZOS)

def tentar_focar_browser():
    for titulo in ["localhost:8501", "Streamlit", "Mozilla Firefox", "Google Chrome", "Microsoft Edge"]:
        wins = gw.getWindowsWithTitle(titulo)
        if wins:
            try:
                wins[0].activate()
                time.sleep(0.8)
                return
            except Exception:
                pass

print("Focando janela do navegador...")
tentar_focar_browser()
time.sleep(1)

print("\nVoce tem 8 segundos para clicar no navegador e deixar o dashboard visivel!")
for i in range(8, 0, -1):
    print(f"  Iniciando em {i}...", end="\r")
    time.sleep(1)
print("\nIniciando captura — nao mova o mouse!")
frames = []

# ── Etapa 1: topo da página (visão geral) ─────────────────────────────────────
print("  [1/4] Topo da pagina...")
for _ in range(FRAMES_POR_ETAPA):
    frames.append(capturar_frame())
    time.sleep(DELAY_FRAME)

# ── Etapa 2: rolar para mostrar os cards de empresa ───────────────────────────
print("  [2/4] Rolando para cards de empresa...")
pyautogui.scroll(-5)
time.sleep(DELAY_SCROLL)
for _ in range(FRAMES_POR_ETAPA):
    frames.append(capturar_frame())
    time.sleep(DELAY_FRAME)

# ── Etapa 3: rolar mais para mostrar grafico ──────────────────────────────────
print("  [3/4] Rolando para grafico...")
pyautogui.scroll(-6)
time.sleep(DELAY_SCROLL)
for _ in range(FRAMES_POR_ETAPA):
    frames.append(capturar_frame())
    time.sleep(DELAY_FRAME)

# ── Etapa 4: voltar ao topo ───────────────────────────────────────────────────
print("  [4/4] Voltando ao topo...")
pyautogui.hotkey("ctrl", "Home")
time.sleep(DELAY_SCROLL)
for _ in range(FRAMES_POR_ETAPA):
    frames.append(capturar_frame())
    time.sleep(DELAY_FRAME)

# ── Salvar GIF ────────────────────────────────────────────────────────────────
print(f"\nGerando GIF com {len(frames)} frames...")
frames[0].save(
    SAIDA,
    save_all=True,
    append_images=frames[1:],
    duration=600,   # ms por frame
    loop=0,         # repetir infinito
    optimize=True,
)

tamanho_kb = os.path.getsize(SAIDA) // 1024
print(f"GIF salvo: {SAIDA}")
print(f"Tamanho: {tamanho_kb} KB | Frames: {len(frames)}")
print("\nPara inserir na apresentacao:")
print("  PowerPoint > Slide 6 > Inserir > Imagens > Este Dispositivo")
print(f"  Arquivo: {SAIDA}")
