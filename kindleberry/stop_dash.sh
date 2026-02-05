#!/bin/sh

# 1. Tenta matar procurando pelo nome do arquivo na lista de processos (Mais garantido)
# Pega todos os PIDs que contenham "show_dash.sh" e mata um por um
pkill -f "show_dash.sh" || \
for pid in $(ps | grep "show_dash.sh" | grep -v grep | awk '{print $1}'); do 
    kill -9 $pid
done

# 2. Mata processos filhos que podem ter ficado travados (wget ou sleep)
killall wget 2>/dev/null
killall sleep 2>/dev/null

# 3. Devolve o controle de energia para o Kindle dormir
lipc-set-prop com.lab126.powerd preventScreenSaver 0
lipc-set-prop com.lab126.cmd wirelessEnable 1

# 4. Limpa a tela
/mnt/us/extensions/kindleberry/fbink -c -f -q "Dashboard Parado"