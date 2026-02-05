#!/bin/sh
# --- Configuração ---
VERSION="v1.0.2"
IP_RPI="192.168.0.XXX"  # <--- SEU IP AQUI
FBINK="/mnt/us/extensions/kindleberry/fbink"
URL_BASE="http://$IP_RPI:5000/dashboard.png"
OUTPUT="/tmp/dashboard.png"

# Configuração do Refresh Híbrido
COUNT=0
REFRESH_LIMIT=10  # Faz um flash completo a cada 10 atualizações (aprox. 50s)

# Previne descanso de tela e liga Wi-Fi
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1

# Primeira mensagem com flash para limpar a tela inicial
$FBINK -c -f -m -q "KindleBerry $VERSION Iniciando..."

while true; do
    # 1. Pega Bateria
    BAT=$(lipc-get-prop com.lab126.powerd capacity)

    # 2. Tenta baixar a imagem
    if wget -q -T 3 -O "$OUTPUT" "$URL_BASE?kbat=$BAT"; then
        
        # Lógica do Refresh Híbrido
        if [ $COUNT -ge $REFRESH_LIMIT ]; then
            # Hora da limpeza: Usa Flash (-f)
            $FBINK -c -f -g file="$OUTPUT"
            COUNT=0
        else
            # Atualização suave: Sem Flash (apenas desenha por cima)
            $FBINK -c -g file="$OUTPUT"
            COUNT=$((COUNT + 1))
        fi

    else
        # Em caso de erro, avisa (sem flash para não irritar)
        $FBINK -c -q "Erro Conexao..."
        lipc-set-prop com.lab126.cmd wirelessEnable 1
    fi

    sleep 5
done