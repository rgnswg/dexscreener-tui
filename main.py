import requests
import curses
import threading
import time
from functools import partial
import logging

logging.basicConfig(
    filename='dexscreener_tui.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

URL = "https://api.dexscreener.com/latest/dex/tokens/"

def chunk_list(lst, n):
    return [lst[i:i + n] for i in range(0, len(lst), n)]

def dexScreenerRequest(tokens):
    try:
        tokens_str = ','.join(tokens)
        response = requests.get(URL + tokens_str)
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            logging.error(f'Error in dexScreenerRequest: status code {response.status_code}')
            return None
    except Exception as e:
        logging.error(f'Error in dexScreenerRequest: {str(e)}')
        return None

def getTokensInfo(tokens):
    """Process information for multiple tokens"""
    data = dexScreenerRequest(tokens)
    if data is None:
        return [None] * len(tokens)
    
    results = []
    try:
        pairs_dict = {pair['baseToken']['address'].lower(): pair 
                     for pair in data['pairs']}
        
        for token in tokens:
            try:
                if token.lower() in pairs_dict:
                    pair = pairs_dict[token.lower()]
                    info = {}
                    baseToken = pair['baseToken']
                    info['symbol'] = baseToken['symbol']
                    info['priceUsd'] = float(pair['priceUsd'])
                    info['url'] = pair['url']
                    info['fdv'] = f"${float(pair['fdv'])/1000000:.1f}M"
                    
                    if 'priceChange' in pair:
                        price_change = pair['priceChange']
                        info['priceChange'] = {
                            '24h': str(price_change.get('h24', '0')),
                            '1h': str(price_change.get('h1', '0')),
                            '5m': str(price_change.get('m5', '0'))
                        }
                    else:
                        info['priceChange'] = {'24h': '0', '1h': '0', '5m': '0'}
                    
                    results.append(info)
                else:
                    results.append(None)
            except (KeyError, ValueError) as e:
                logging.error(f'Error processing token {token}: {str(e)}')
                results.append(None)
                
    except Exception as e:
        logging.error(f'Error processing API response: {str(e)}')
        return [None] * len(tokens)
    
    return results

def getInfoFromAddys(addys):
    """Process addresses in groups of 30"""
    MAX_TOKENS_PER_REQUEST = 30
    all_results = []
    
    address_chunks = chunk_list(addys, MAX_TOKENS_PER_REQUEST)
    
    for chunk in address_chunks:
        chunk_results = getTokensInfo(chunk)
        all_results.extend(chunk_results)
        
    return all_results

def getAddresses(path):
    """Read addresses from file, ignoring commented and empty lines."""
    addresses = []
    try:
        with open(path, 'r') as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = [part for part in line.split() if part]
                    if parts:
                        addresses.append(parts[0])
    except FileNotFoundError:
        logging.error(f'Error: Address file not found at {path}')
    except Exception as e:
        logging.error(f'Error reading address file: {str(e)}')
    return addresses

def getColW(stdscr):
    h,w = stdscr.getmaxyx()
    colWidths = [10,10,12,6,6,6]
    totalWidth = sum(colWidths)
    scaleFactor = w/totalWidth
    colWidthsScaled = [int(w * scaleFactor) for w in colWidths]
    return colWidthsScaled

def drawFrame(stdscr):
    h, w = stdscr.getmaxyx()
    tl, tr = '┌', '┐'  
    bl, br = '└', '┘'  
    h_line = '─'       
    v_line = '│'       
    
    stdscr.addstr(0, 0, tl + h_line * (w-2) + tr)
    for y in range(1, h-1):
        stdscr.addstr(y, 0, v_line)
        stdscr.addstr(y, w-1, v_line)

    stdscr.addstr(2, 0, v_line + h_line * (w-2) + v_line)
    footer = " Press 'q' to exit "
    footer_pos = w - len(footer) - 2
    bottom_line = (bl + 
                  h_line * (footer_pos - 1) + 
                  footer + 
                  h_line * (w - footer_pos - len(footer) - 2) + 
                  br)
    stdscr.addstr(h-1, 0, bottom_line[:-1])
    try:
        stdscr.addstr(h-1, w-1, br)
    except curses.error:
        pass

def drawHeader(stdscr):
    h, w = stdscr.getmaxyx()
    headers = ['$TOKEN', 'FDV', 'PRICE(USD)', '24h', '1h', '5m']
    colWidthsScaled = getColW(stdscr)
    colStart = 3
    title = "Dexscreener-TUI"
    title_pos = (w - len(title)) // 2
    stdscr.addstr(1, title_pos, title)
    for i, header in enumerate(headers):
        stdscr.addstr(3, colStart, header[:colWidthsScaled[i]])
        colStart += colWidthsScaled[i]

def updateScreen(stdscr, data):
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    drawFrame(stdscr)
    drawHeader(stdscr)
    colW = getColW(stdscr)
    row = 4
    for token in data:
        if token is None:
            continue
        if row >= h-2: 
            break
            
        colStart = 3
        stdscr.addstr(row, colStart, '$'+token['symbol'])
        colStart += colW[0]
        stdscr.addstr(row, colStart, token['fdv'])
        colStart += colW[1]
        stdscr.addstr(row, colStart, f"${token['priceUsd']:.8f}")
        colStart += colW[2]
        
        pc = token['priceChange']
        changes = [pc['24h'], pc['1h'], pc['5m']]
        for change in changes:
            try:
                value = float(change)
                color = curses.COLOR_GREEN if value >= 0 else curses.COLOR_RED
                stdscr.addstr(row, colStart, f"{value:+.2f}%", curses.color_pair(color))
            except (ValueError, TypeError):
                stdscr.addstr(row, colStart, "0.00%")
            colStart += colW[3 if change == pc['24h'] else 4 if change == pc['1h'] else 5]
        row += 1
    
    stdscr.refresh()

def main(stdscr):
    curses.use_default_colors()
    curses.init_pair(curses.COLOR_GREEN, curses.COLOR_GREEN, -1)
    curses.init_pair(curses.COLOR_RED, curses.COLOR_RED, -1)
    
    data = []
    addys = getAddresses('cas.txt')
    curses.curs_set(0)

    stdscr.bkgd(' ', curses.color_pair(0))
    def apiThread(addys):
        nonlocal data
        while True:
            newData = getInfoFromAddys(addys)
            if newData is not None:
                data = newData
            time.sleep(5)
    thread = threading.Thread(target=partial(apiThread,addys), daemon=True)
    thread.start()
    stdscr.nodelay(1)
    curses.resizeterm(*stdscr.getmaxyx())
    while True:
        try:
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == curses.KEY_RESIZE:
                curses.update_lines_cols()
                stdscr.clear()
                updateScreen(stdscr, data)
                continue
        except curses.error:
            pass
        updateScreen(stdscr, data)
        time.sleep(1)
curses.wrapper(main)

