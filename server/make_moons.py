from PIL import Image, ImageDraw
import os

# Configuração
SIZE = 100  # Tamanho do ícone (px)
BG_COLOR = 255 # Fundo branco (o Kindle inverte depois se precisar)
FG_COLOR = 0   # Lua preta (para destacar no fundo branco)
# Nota: No nosso sistema, o ícone é "recortado" depois. 
# Vamos fazer o padrão: Lua CHEIA = Círculo Preto. Lua NOVA = Círculo Branco (vazio).

if not os.path.exists("icons"):
    os.makedirs("icons")

def create_moon(filename, phase):
    # phase: 0=New, 4=Full, etc.
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0)) # Fundo transparente
    draw = ImageDraw.Draw(img)
    
    # Coordenadas
    padding = 10
    bbox = (padding, padding, SIZE-padding, SIZE-padding)
    
    # 1. Desenha o círculo base (A "Sombra")
    # Para ícones, vamos desenhar a lua em PRETO (ou branco dependendo do tema).
    # Vamos fazer estilo "Flat Black"
    
    # Lua Nova (New): Tudo vazio ou contorno? Vamos fazer vazio.
    if filename == "moon_new":
        draw.ellipse(bbox, outline="black", width=3)
        
    # Lua Cheia (Full): Tudo preenchido
    elif filename == "moon_full":
        draw.ellipse(bbox, fill="black", outline="black")
        
    # Quartos (Metade)
    elif filename == "moon_first_quarter": # Crescente (Direita iluminada)
        draw.chord(bbox, start=270, end=90, fill="black", outline="black")
        draw.arc(bbox, start=90, end=270, fill="black", width=3) # Contorno do resto
        
    elif filename == "moon_last_quarter": # Minguante (Esquerda iluminada)
        draw.chord(bbox, start=90, end=270, fill="black", outline="black")
        draw.arc(bbox, start=270, end=90, fill="black", width=3)
        
    # Crescentes (Côncavas)
    elif filename == "moon_waxing_crescent":
        # Um arco preenchido deslocando uma elipse branca
        draw.ellipse(bbox, outline="black", width=3)
        # Gambiarra visual: Desenha cheia e "come" com outra elipse
        # Mas para simplificar em vetor flat:
        draw.chord(bbox, start=270, end=90, fill="black") # Metade direita
        # "Apaga" a parte interna com um círculo branco deslocado
        offset = SIZE * 0.25
        eraser_box = (padding - offset, padding, SIZE-padding - offset, SIZE-padding)
        # Ops, mais fácil desenhar arco grosso
        
    # GIBOSAS (Convexas)
    
    # --- MÉTODO SIMPLIFICADO GEOMÉTRICO (Melhor para ícones pequenos) ---
    # Vamos refazer a lógica para ficar visualmente bonito e simples
    
    img = Image.new("RGBA", (SIZE, SIZE), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    
    # Desenha contorno base sempre
    draw.ellipse(bbox, outline="black", width=4)
    
    if filename == "moon_new":
        pass # Só contorno
        
    elif filename == "moon_full":
        draw.ellipse(bbox, fill="black")
        
    elif filename == "moon_first_quarter": # Direita cheia
        draw.chord(bbox, start=270, end=90, fill="black")
        
    elif filename == "moon_last_quarter": # Esquerda cheia
        draw.chord(bbox, start=90, end=270, fill="black")
        
    elif filename == "moon_waxing_crescent": # Unha na direita
        # Desenha metade direita
        draw.chord(bbox, start=270, end=90, fill="black")
        # Desenha elipse branca por cima para "cavar"
        w = (SIZE - 2*padding)
        h = (SIZE - 2*padding)
        # Elipse ovalada branca
        draw.ellipse((padding + w*0.3, padding, padding + w*1.0, padding+h), fill=(0,0,0,0)) # Transparente não apaga...
        # PIL não tem "borracha" simples em modo RGBA sem mask.
        # Vamos fazer pixel a pixel ou poligono? Não, vamos usar máscara.
        pass # (Veja lógica abaixo corrigida)

    return img

# --- FUNÇÃO DE DESENHO CORRETA (COM MÁSCARA) ---
def draw_phase(name):
    img = Image.new("RGBA", (SIZE, SIZE), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    p = 10 # padding
    w = SIZE - 2*p
    
    # Contorno
    draw.ellipse((p, p, p+w, p+w), outline="black", width=5)
    
    if name == "moon_new": return img
    if name == "moon_full": 
        draw.ellipse((p+2, p+2, p+w-2, p+w-2), fill="black")
        return img
    
    # Para as fases parciais, usamos interseção de elipses
    # Mas para facilitar sua vida, vamos fazer um estilo "Pixel Art" simplificado 
    # que fica ÓTIMO no Kindle e não dá erro matemático
    
    # Metades
    if name == "moon_first_quarter":
        draw.pieslice((p, p, p+w, p+w), 270, 90, fill="black")
    elif name == "moon_last_quarter":
        draw.pieslice((p, p, p+w, p+w), 90, 270, fill="black")
        
    # Crescentes (Unha)
    elif name == "moon_waxing_crescent":
        draw.pieslice((p, p, p+w, p+w), 270+45, 90-45, fill="black") # Fatia menor direita
    elif name == "moon_waning_crescent":
        draw.pieslice((p, p, p+w, p+w), 90+45, 270-45, fill="black") # Fatia menor esquerda
        
    # Gibosas (Barriga)
    elif name == "moon_waxing_gibbous":
        draw.ellipse((p, p, p+w, p+w), fill="black") # Cheia
        # Teria que "pintar de branco" a unha esquerda... difícil no PIL simples.
        # Vamos fazer um "Pacman" fechado
        draw.pieslice((p+2, p+2, p+w-2, p+w-2), 90+45, 270-45, fill="white") # Remove fatia esq
        draw.ellipse((p, p, p+w, p+w), outline="black", width=5) # Redesenha contorno
        
    elif name == "moon_waning_gibbous":
        draw.ellipse((p, p, p+w, p+w), fill="black")
        draw.pieslice((p+2, p+2, p+w-2, p+w-2), 270+45, 90-45, fill="white") # Remove fatia dir
        draw.ellipse((p, p, p+w, p+w), outline="black", width=5)

    return img

# Lista de arquivos
moons = [
    "moon_new", "moon_waxing_crescent", "moon_first_quarter", "moon_waxing_gibbous",
    "moon_full", "moon_waning_gibbous", "moon_last_quarter", "moon_waning_crescent"
]

print("Gerando ícones...")
for m in moons:
    img = draw_phase(m)
    img.save(f"icons/{m}.png")
    print(f"- icons/{m}.png")
    
print("Pronto! Reinicie o servidor para carregar.")