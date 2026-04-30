"""
hw1_11427234_v24.py — Dual-Track Defense (v24: 雙軌防禦機制)
結合 v22 的「階段基礎防禦」與 v21 的「威脅動態提升」。
開局保底高防禦 (1.5) 壓制黑子；中後盤依賴對手分數動態拉高防禦 (最高 1.6) 以封堵致命攻擊。
"""
import sys
import time
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_HW1_DIR = _THIS_DIR / "hw1"
if str(_HW1_DIR) not in sys.path:
    sys.path.insert(0, str(_HW1_DIR))

from common import (
    EMPTY, BLACK, WHITE,
    opponent, in_bounds, board_full,
    is_empty_board, is_legal_move, legal_moves,
    is_win_after_move, occupied_neighbors,
)

MAX_DEPTH       = 7     
MAX_CANDIDATES  = 10    
QSEARCH_DEPTH   = 3     
NEIGHBOR_RADIUS = 2     
TIME_BUDGET     = 4.5
_baseline_opp_weight = 1.2

INF        = 10 ** 18
WIN_SCORE  = 100_000_000
DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]

def _lcg_seq(seed: int, n: int) -> list:
    x = seed; out = []
    for _ in range(n):
        x = (x * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        out.append(x)
    return out

_BS = 15
_rnd = _lcg_seq(0x9E3779B9_7F4A7C15, _BS * _BS * 3)
ZOBRIST = [[[0, _rnd[(y * _BS + x) * 3 + 1], _rnd[(y * _BS + x) * 3 + 2]] for x in range(_BS)] for y in range(_BS)]
EXACT, LOWER, UPPER = 0, 1, 2
TT_MAX = 1_000_000
_TT: dict = {}
_start_time: float = 0.0
_time_up: bool = False

def read_board(stream, size: int):
    stream.readline()
    board = [list(map(int, stream.readline().split())) for _ in range(size)]
    stream.readline()
    return board

def segment_score(length: int, open_ends: int) -> int:
    if length >= 5: return 10_000_000
    if length == 4: return 2_000_000 if open_ends == 2 else 200_000
    if length == 3: return 50_000    if open_ends == 2 else 3_000
    if length == 2: return 500       if open_ends == 2 else 80
    if length == 1: return 15        if open_ends == 2 else 0
    return 0

def score_color(board, color: int) -> int:
    size = len(board); total = 0
    for y in range(size):
        for x in range(size):
            if board[y][x] != color: continue
            for dx, dy in DIRECTIONS:
                px, py = x - dx, y - dy
                if in_bounds(px, py, size) and board[py][px] == color: continue
                length = 0; cx, cy = x, y
                while in_bounds(cx, cy, size) and board[cy][cx] == color:
                    length += 1; cx += dx; cy += dy
                oe = 0
                if in_bounds(px, py, size) and board[py][px] == EMPTY: oe += 1
                if in_bounds(cx, cy, size) and board[cy][cx] == EMPTY: oe += 1
                total += segment_score(length, oe)
    return total

def evaluate(board, player: int) -> int:
    global _baseline_opp_weight
    mine = score_color(board, player)
    opp  = score_color(board, opponent(player))
    
    # 威脅感知權重 (Threat Weight)
    if opp >= 200_000:
        threat_weight = 1.6     # 致命威脅
    elif opp >= 50_000:
        threat_weight = 1.4     # 強烈威脅
    elif opp >= 3_000:
        threat_weight = 1.3     # 一般威脅
    else:
        threat_weight = 1.0     # 無明顯威脅
        
    # 最終防禦權重為兩者取大
    final_weight = max(_baseline_opp_weight, threat_weight)
    
    return mine - int(opp * final_weight)

def generate_candidate_moves(board, radius: int) -> list:
    size = len(board)
    if is_empty_board(board): return [(size // 2, size // 2)]
    moves: set = set()
    for y in range(size):
        for x in range(size):
            if board[y][x] == EMPTY: continue
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    nx, ny = x + dx, y + dy
                    if in_bounds(nx, ny, size) and board[ny][nx] == EMPTY: moves.add((nx, ny))
    return list(moves)

def local_line_value(board, x: int, y: int, color: int) -> int:
    size = len(board); total = 0
    for dx, dy in DIRECTIONS:
        left = 0; cx, cy = x - dx, y - dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color: left += 1; cx -= dx; cy -= dy
        right = 0; cx, cy = x + dx, y + dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color: right += 1; cx += dx; cy += dy
        length = 1 + left + right
        lx, ly = x - (left + 1) * dx, y - (left + 1) * dy
        rx, ry = x + (right + 1) * dx, y + (right + 1) * dy
        oe = 0
        if in_bounds(lx, ly, size) and board[ly][lx] == EMPTY: oe += 1
        if in_bounds(rx, ry, size) and board[ry][rx] == EMPTY: oe += 1
        total += segment_score(length, oe)
    return total

def is_threat_move(board, x: int, y: int, color: int) -> bool:
    size = len(board)
    for dx, dy in DIRECTIONS:
        left = 0; cx, cy = x - dx, y - dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color: left += 1; cx -= dx; cy -= dy
        right = 0; cx, cy = x + dx, y + dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color: right += 1; cx += dx; cy += dy
        if 1 + left + right >= 4: return True
    return False

def get_threat_moves(board, player: int) -> list:
    opp = opponent(player); threats = []
    for x, y in generate_candidate_moves(board, NEIGHBOR_RADIUS):
        if not is_legal_move(board, x, y, player): continue
        board[y][x] = player
        if is_win_after_move(board, x, y, player):
            board[y][x] = EMPTY; return [(x, y)]
        atk_four = is_threat_move(board, x, y, player)
        board[y][x] = EMPTY
        board[y][x] = opp
        opp_win  = is_win_after_move(board, x, y, opp)
        opp_four = is_threat_move(board, x, y, opp)
        board[y][x] = EMPTY
        if opp_win or atk_four or opp_four: threats.append((x, y))
    return threats

def move_priority(board, x: int, y: int, player: int) -> int:
    size = len(board); center = size // 2; opp = opponent(player)
    board[y][x] = player
    self_win = is_win_after_move(board, x, y, player)
    self_score = local_line_value(board, x, y, player)
    board[y][x] = EMPTY
    if self_win: return 10 ** 12
    board[y][x] = opp
    opp_win = is_win_after_move(board, x, y, opp)
    block_score = local_line_value(board, x, y, opp)
    board[y][x] = EMPTY
    n1 = occupied_neighbors(board, x, y, 1)
    n2 = occupied_neighbors(board, x, y, 2)
    cb = size - (abs(x - center) + abs(y - center))
    return (10 ** 11 if opp_win else 0) + self_score * 5 + block_score * 4 + n1 * 120 + n2 * 25 + cb

def ordered_moves(board, player: int) -> list:
    moves = [(x, y) for x, y in generate_candidate_moves(board, NEIGHBOR_RADIUS) if is_legal_move(board, x, y, player)]
    if not moves: moves = legal_moves(board, player)
    scored = [(move_priority(board, x, y, player), x, y) for x, y in moves]
    scored.sort(reverse=True)
    return [(x, y) for _, x, y in scored[:MAX_CANDIDATES]]

def quiescence(board, qdepth: int, alpha: int, beta: int, player: int) -> int:
    global _time_up
    if _time_up: return 0
    if time.perf_counter() - _start_time > TIME_BUDGET: _time_up = True; return 0

    stand_pat = evaluate(board, player)
    if stand_pat >= beta: return beta
    if stand_pat > alpha: alpha = stand_pat
    if qdepth <= 0: return stand_pat

    threat_moves = get_threat_moves(board, player)
    if not threat_moves: return stand_pat

    opp = opponent(player)
    for x, y in threat_moves:
        board[y][x] = player
        if is_win_after_move(board, x, y, player):
            board[y][x] = EMPTY; return WIN_SCORE
        val = -quiescence(board, qdepth - 1, -beta, -alpha, opp)
        board[y][x] = EMPTY
        if _time_up: return alpha
        if val >= beta: return beta
        if val > alpha: alpha = val
    return alpha

def pvs(board, depth: int, alpha: int, beta: int, player: int, zh: int, root_depth: int) -> int:
    global _time_up
    if _time_up: return 0
    if time.perf_counter() - _start_time > TIME_BUDGET: _time_up = True; return 0
    if board_full(board): return 0

    if depth == 0: return quiescence(board, QSEARCH_DEPTH, alpha, beta, player)

    tt_entry = _TT.get(zh)
    if tt_entry is not None:
        ts, td, tf = tt_entry
        if td >= depth:
            if tf == EXACT: return ts
            if tf == LOWER and ts > alpha: alpha = ts
            elif tf == UPPER and ts < beta: beta = ts
            if alpha >= beta: return ts

    moves = ordered_moves(board, player)
    if not moves: return 0

    best = -INF; orig_alpha = alpha; opp = opponent(player); first = True
    for x, y in moves:
        new_zh = zh ^ ZOBRIST[y][x][player]
        board[y][x] = player
        if is_win_after_move(board, x, y, player): val = WIN_SCORE - (root_depth - depth)
        elif first:
            val = -pvs(board, depth - 1, -beta, -alpha, opp, new_zh, root_depth)
            first = False
        else:
            val = -pvs(board, depth - 1, -alpha - 1, -alpha, opp, new_zh, root_depth)
            if not _time_up and alpha < val < beta:
                val = -pvs(board, depth - 1, -beta, -alpha, opp, new_zh, root_depth)
        board[y][x] = EMPTY

        if _time_up: return best if best > -INF else 0
        if val > best: best = val
        if best > alpha: alpha = best
        if alpha >= beta: break

    if not _time_up and len(_TT) < TT_MAX:
        flag = UPPER if best <= orig_alpha else (LOWER if best >= beta else EXACT)
        _TT[zh] = (best, depth, flag)
    return best

def init_zobrist_hash(board) -> int:
    h = 0
    for y, row in enumerate(board):
        for x, c in enumerate(row): h ^= ZOBRIST[y][x][c]
    return h

def choose_move(board, my_color: int):
    global _start_time, _time_up, _TT, _baseline_opp_weight
    _start_time = time.perf_counter()
    _time_up    = False
    _TT         = {}
    
    # 計算階段基礎權重 (Baseline Weight)
    total_pieces = sum(1 for row in board for c in row if c != EMPTY)
    if total_pieces < 15:
        _baseline_opp_weight = 1.5   # 開局保底高防禦
    elif total_pieces <= 40:
        _baseline_opp_weight = 1.3   # 中盤保底防禦
    else:
        _baseline_opp_weight = 1.2   # 殘局保底低防禦，以利反擊

    if is_empty_board(board): return len(board) // 2, len(board) // 2
    zh = init_zobrist_hash(board); opp = opponent(my_color); best_move = None

    for depth in range(1, MAX_DEPTH + 1):
        if time.perf_counter() - _start_time > TIME_BUDGET: break
        moves = ordered_moves(board, my_color)
        if not moves: break

        best_score = -INF; candidate = moves[0]; alpha = -INF; beta = INF; first = True

        for x, y in moves:
            new_zh = zh ^ ZOBRIST[y][x][my_color]
            board[y][x] = my_color
            if is_win_after_move(board, x, y, my_color): score = WIN_SCORE
            elif first:
                score = -pvs(board, depth - 1, -beta, -alpha, opp, new_zh, depth)
                first = False
            else:
                score = -pvs(board, depth - 1, -alpha - 1, -alpha, opp, new_zh, depth)
                if not _time_up and alpha < score < beta:
                    score = -pvs(board, depth - 1, -beta, -alpha, opp, new_zh, depth)
            board[y][x] = EMPTY

            if _time_up: break
            if score > best_score: best_score = score; candidate = (x, y)
            if score > alpha: alpha = score

        if not _time_up:
            best_move = candidate
            if best_score >= WIN_SCORE - MAX_DEPTH: break

    if best_move is None:
        fallback = legal_moves(board, my_color)
        if not fallback: raise RuntimeError("no legal moves")
        return fallback[0]
    return best_move

def main():
    board_size = None; my_color = None
    for raw in sys.stdin:
        line = raw.strip()
        if not line: continue
        parts = line.split()
        if parts[0] == "START":
            board_size = int(parts[1])
            my_color = BLACK if parts[2].upper() == "BLACK" else WHITE
        elif parts[0] == "TURN":
            board = read_board(sys.stdin, board_size)
            x, y = choose_move(board, my_color)
            print(f"MOVE {x} {y}", flush=True)
        elif parts[0] == "END": break

if __name__ == "__main__": main()
