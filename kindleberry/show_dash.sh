#!/bin/sh

# CONFIG
VERSION="v1.0.1"
IP_RPI="192.168.0.249"
FBINK="/mnt/us/extensions/kindleberry/fbink"
URL="http://$IP_RPI:5000/dashboard.png"
OUTPUT="/tmp/dashboard.png"

lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.cmd wirelessEnable 1

$FBINK -c -f -m -q "Carregando..."

while true; do
    if wget -q -T 3 -O "$OUTPUT" "$URL"; then
        # -c = limpa buffer
        # -f = FLASH (remove fantasmas)
        # -g = desenha
        $FBINK -c -f -g file="$OUTPUT"
    else
        $FBINK -c -q "Erro Conexao..."
        lipc-set-prop com.lab126.cmd wirelessEnable 1
    fi
    
    # 15 SEGUNDOS
    sleep 15
done
