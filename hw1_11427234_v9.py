"""
hw1_11427234_v9.py  — Version 9: PVS + Quiescence Search (全新合體版)

【全新策略 #1】：修復並合體 v5 (PVS) + v7 (Quiescence)

v5 的失敗分析：
  - PVS 零窗口測試正確，但缺少 Quiescence Search
  - 在深度截止時直接靜態估分，水平線效應嚴重
  - 結果：3局全敗

改進點：
  1. PVS (Principal Variation Search) 讓主搜尋更快
  2. 同時加入 Quiescence Search 消除水平線效應
  3. OPP_WEIGHT=1.3（積極防守）
  4. MAX_CANDIDATES=10（換取更深搜尋）
  5. 修復 PVS 的 re-search 邊界條件

指標記錄欄位（由 benchmark_engines.py 自動收集）：
  - 執行時間 (white_avg_time, white_max_time)
  - 步數 (white_moves)
  - 分數 (score)
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

# ──────────────────────────────────────────────────────────
# 參數設定
# ──────────────────────────────────────────────────────────
MAX_DEPTH       = 7      # PVS 剪枝效率高，可搜更深
MAX_CANDIDATES  = 10     # 降低候選換取更深搜尋
QSEARCH_DEPTH   = 3      # 靜止搜尋額外深度
NEIGHBOR_RADIUS = 2
TIME_BUDGET     = 4.8
INF             = 10 ** 18
WIN_SCORE       = 100_000_000
OPP_WEIGHT      = 1.3    # 積極防守

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]
EXACT, LOWER, UPPER = 0, 1, 2
TT_MAX = 1_000_000

# ──────────────────────────────────────────────────────────
# Zobrist Hashing
# ──────────────────────────────────────────────────────────
def _lcg(seed, n):
    x, out = seed, []
    for _ in range(n):
        x = (x * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        out.append(x)
    return out

_BS = 15
_rnd = _lcg(0x9E3779B9_7F4A7C15, _BS * _BS * 3)
ZOBRIST = [[[0, _rnd[(y*_BS+x)*3+1], _rnd[(y*_BS+x)*3+2]]
            for x in range(_BS)] for y in range(_BS)]

_TT: dict = {}
_start_time: float = 0.0
_time_up: bool = False


# ──────────────────────────────────────────────────────────
# I/O
# ──────────────────────────────────────────────────────────
def read_board(stream, size):
    stream.readline()  # BOARD
    board = [list(map(int, stream.readline().split())) for _ in range(size)]
    stream.readline()  # END_BOARD
    return board


# ──────────────────────────────────────────────────────────
# 評分函式
# ──────────────────────────────────────────────────────────
def segment_score(length, open_ends):
    if length >= 5: return 10_000_000
    if length == 4: return 2_000_000 if open_ends == 2 else 200_000
    if length == 3: return 50_000    if open_ends == 2 else 3_000
    if length == 2: return 500       if open_ends == 2 else 80
    if length == 1: return 15        if open_ends == 2 else 0
    return 0


def score_color(board, color):
    size, total = len(board), 0
    for y in range(size):
        for x in range(size):
            if board[y][x] != color: continue
            for dx, dy in DIRECTIONS:
                px, py = x-dx, y-dy
                if in_bounds(px, py, size) and board[py][px] == color: continue
                length, cx, cy = 0, x, y
                while in_bounds(cx, cy, size) and board[cy][cx] == color:
                    length += 1; cx += dx; cy += dy
                oe = 0
                if in_bounds(px, py, size) and board[py][px] == EMPTY: oe += 1
                if in_bounds(cx, cy, size) and board[cy][cx] == EMPTY: oe += 1
                total += segment_score(length, oe)
    return total


def evaluate(board, player):
    return score_color(board, player) - int(score_color(board, opponent(player)) * OPP_WEIGHT)


# ──────────────────────────────────────────────────────────
# 候選著法
# ──────────────────────────────────────────────────────────
def generate_candidates(board, radius):
    size = len(board)
    if is_empty_board(board): c = size//2; return [(c, c)]
    moves = set()
    for y in range(size):
        for x in range(size):
            if board[y][x] == EMPTY: continue
            for dy in range(-radius, radius+1):
                for dx in range(-radius, radius+1):
                    nx, ny = x+dx, y+dy
                    if in_bounds(nx, ny, size) and board[ny][nx] == EMPTY:
                        moves.add((nx, ny))
    return list(moves)


def local_line_value(board, x, y, color):
    size, total = len(board), 0
    for dx, dy in DIRECTIONS:
        left, cx, cy = 0, x-dx, y-dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color:
            left += 1; cx -= dx; cy -= dy
        right, cx, cy = 0, x+dx, y+dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color:
            right += 1; cx += dx; cy += dy
        length = 1+left+right
        lx, ly = x-(left+1)*dx, y-(left+1)*dy
        rx, ry = x+(right+1)*dx, y+(right+1)*dy
        oe = 0
        if in_bounds(lx, ly, size) and board[ly][lx] == EMPTY: oe += 1
        if in_bounds(rx, ry, size) and board[ry][rx] == EMPTY: oe += 1
        total += segment_score(length, oe)
    return total


def is_threat_move(board, x, y, color):
    """已在 board[y][x]=color 的情況下，檢查是否形成四連以上"""
    size = len(board)
    for dx, dy in DIRECTIONS:
        left, cx, cy = 0, x-dx, y-dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color:
            left += 1; cx -= dx; cy -= dy
        right, cx, cy = 0, x+dx, y+dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color:
            right += 1; cx += dx; cy += dy
        if 1+left+right >= 4:
            return True
    return False


def get_threat_moves(board, player):
    opp = opponent(player)
    raw = generate_candidates(board, NEIGHBOR_RADIUS)
    threats = []
    for x, y in raw:
        if not is_legal_move(board, x, y, player): continue
        board[y][x] = player
        if is_win_after_move(board, x, y, player):
            board[y][x] = EMPTY
            return [(x, y)]
        atk = is_threat_move(board, x, y, player)
        board[y][x] = EMPTY
        board[y][x] = opp
        ow = is_win_after_move(board, x, y, opp)
        ot = is_threat_move(board, x, y, opp)
        board[y][x] = EMPTY
        if ow or atk or ot:
            threats.append((x, y))
    return threats


def move_priority(board, x, y, player):
    size = len(board); opp = opponent(player)
    board[y][x] = player
    sw = is_win_after_move(board, x, y, player)
    ss = local_line_value(board, x, y, player)
    board[y][x] = EMPTY
    if sw: return 10**12
    board[y][x] = opp
    ow = is_win_after_move(board, x, y, opp)
    bs = local_line_value(board, x, y, opp)
    board[y][x] = EMPTY
    n1 = occupied_neighbors(board, x, y, 1)
    n2 = occupied_neighbors(board, x, y, 2)
    cb = size - (abs(x-size//2)+abs(y-size//2))
    return (10**11 if ow else 0) + ss*5 + bs*4 + n1*120 + n2*25 + cb


def ordered_moves(board, player):
    raw = generate_candidates(board, NEIGHBOR_RADIUS)
    moves = [(x, y) for x, y in raw if is_legal_move(board, x, y, player)]
    if not moves: moves = legal_moves(board, player)
    scored = [(move_priority(board, x, y, player), x, y) for x, y in moves]
    scored.sort(reverse=True)
    return [(x, y) for _, x, y in scored[:MAX_CANDIDATES]]


def init_zh(board):
    h = 0
    for y, row in enumerate(board):
        for x, c in enumerate(row): h ^= ZOBRIST[y][x][c]
    return h


# ──────────────────────────────────────────────────────────
# 靜止搜尋 (Quiescence Search)
# ──────────────────────────────────────────────────────────
def quiescence(board, qdepth, alpha, beta, player):
    global _time_up
    if _time_up: return 0
    if time.perf_counter() - _start_time > TIME_BUDGET:
        _time_up = True; return 0

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
            board[y][x] = EMPTY
            return WIN_SCORE
        val = -quiescence(board, qdepth-1, -beta, -alpha, opp)
        board[y][x] = EMPTY
        if _time_up: return alpha
        if val >= beta: return beta
        if val > alpha: alpha = val
    return alpha


# ──────────────────────────────────────────────────────────
# PVS + Quiescence (核心搜尋)
# ──────────────────────────────────────────────────────────
def pvs(board, depth, alpha, beta, player, zh, root_depth):
    """
    Principal Variation Search:
    - 第一個著法用完整窗口
    - 後續著法先用零窗口 [alpha, alpha+1]，僅在有改善時重搜
    - depth=0 時啟動 quiescence search 而非直接估分
    """
    global _time_up
    if _time_up: return 0
    if time.perf_counter() - _start_time > TIME_BUDGET:
        _time_up = True; return 0
    if board_full(board): return 0

    # depth=0 進入靜止搜尋（避免水平線效應）
    if depth == 0:
        return quiescence(board, QSEARCH_DEPTH, alpha, beta, player)

    # 轉置表查找
    tt = _TT.get(zh)
    if tt is not None:
        ts, td, tf = tt
        if td >= depth:
            if tf == EXACT: return ts
            if tf == LOWER and ts > alpha: alpha = ts
            elif tf == UPPER and ts < beta: beta = ts
            if alpha >= beta: return ts

    moves = ordered_moves(board, player)
    if not moves: return 0

    best, orig_alpha = -INF, alpha
    opp = opponent(player)
    first = True

    for x, y in moves:
        nh = zh ^ ZOBRIST[y][x][player]
        board[y][x] = player
        if is_win_after_move(board, x, y, player):
            val = WIN_SCORE - (root_depth - depth)
        elif first:
            # PV 節點：完整窗口
            val = -pvs(board, depth-1, -beta, -alpha, opp, nh, root_depth)
            first = False
        else:
            # 非 PV 節點：零窗口測試
            val = -pvs(board, depth-1, -alpha-1, -alpha, opp, nh, root_depth)
            # 若可能改善 alpha 且未被截斷，重新完整搜尋
            if not _time_up and alpha < val < beta:
                val = -pvs(board, depth-1, -beta, -alpha, opp, nh, root_depth)
        board[y][x] = EMPTY

        if _time_up: return best if best > -INF else 0
        if val > best: best = val
        if best > alpha: alpha = best
        if alpha >= beta: break

    if not _time_up and len(_TT) < TT_MAX:
        flag = UPPER if best <= orig_alpha else (LOWER if best >= beta else EXACT)
        _TT[zh] = (best, depth, flag)
    return best


# ──────────────────────────────────────────────────────────
# 主選手函式 (IDDFS)
# ──────────────────────────────────────────────────────────
def choose_move(board, my_color):
    global _start_time, _time_up, _TT
    _start_time = time.perf_counter()
    _time_up = False; _TT = {}
    size = len(board)
    if is_empty_board(board): c = size//2; return c, c

    zh = init_zh(board)
    opp = opponent(my_color)
    best_move = None

    for depth in range(1, MAX_DEPTH+1):
        if time.perf_counter() - _start_time > TIME_BUDGET: break
        moves = ordered_moves(board, my_color)
        if not moves: break
        best_score, cand = -INF, moves[0]
        alpha, beta = -INF, INF
        first = True

        for x, y in moves:
            nh = zh ^ ZOBRIST[y][x][my_color]
            board[y][x] = my_color
            if is_win_after_move(board, x, y, my_color):
                score = WIN_SCORE
            elif first:
                score = -pvs(board, depth-1, -beta, -alpha, opp, nh, depth)
                first = False
            else:
                score = -pvs(board, depth-1, -alpha-1, -alpha, opp, nh, depth)
                if not _time_up and alpha < score < beta:
                    score = -pvs(board, depth-1, -beta, -alpha, opp, nh, depth)
            board[y][x] = EMPTY
            if _time_up: break
            if score > best_score:
                best_score = score; cand = (x, y)
            if score > alpha: alpha = score

        if not _time_up:
            best_move = cand
            if best_score >= WIN_SCORE - MAX_DEPTH: break

    if best_move is None:
        fb = legal_moves(board, my_color)
        if not fb: raise RuntimeError("no legal moves")
        return fb[0]
    return best_move


# ──────────────────────────────────────────────────────────
# 主程式
# ──────────────────────────────────────────────────────────
def main():
    board_size = my_color = None
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
        elif parts[0] == "END":
            break


if __name__ == "__main__":
    main()
