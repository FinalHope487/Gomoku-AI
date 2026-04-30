"""
engine_v20.py  — Phase-Adaptive Evaluation 版本 (v20: PVS + Quiescence + Phase Adaptive)
算法：根據棋盤現有棋子數量動態調整防禦權重(OPP_WEIGHT)。
評分：增強版分值表（live-4 = 2M, live-3 = 50K）
動態防守：開局 1.1，中局 1.3，殘局 1.5
時間：每步最多 3.8 秒，安全餘裕 1.2 秒
靜止搜尋：depth=0 時繼續搜尋威脅著法（避免水平線效應）
PVS：PV 節點完整窗口，非 PV 節點零窗口加速剪枝
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
MAX_DEPTH       = 7     # PVS 剪枝效率高，可搜更深
MAX_CANDIDATES  = 10    # 每層最多考慮幾個候選著（減少換取更深搜尋）
QSEARCH_DEPTH   = 3     # 靜止搜尋額外深度
NEIGHBOR_RADIUS = 2     # 候選著法產生半徑
TIME_BUDGET     = 3.8   # 每步時間上限（秒），留 1.2 秒餘裕

INF        = 10 ** 18
WIN_SCORE  = 100_000_000
_current_opp_weight = 1.3        # 動態防守權重

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]

# ──────────────────────────────────────────────────────────
# Zobrist Hashing（確定性，不使用 random 模組）
# ──────────────────────────────────────────────────────────
def _lcg_seq(seed: int, n: int) -> list:
    x = seed
    out = []
    for _ in range(n):
        x = (x * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        out.append(x)
    return out

_BS = 15
_rnd = _lcg_seq(0x9E3779B9_7F4A7C15, _BS * _BS * 3)
ZOBRIST = [
    [[0,
      _rnd[(y * _BS + x) * 3 + 1],
      _rnd[(y * _BS + x) * 3 + 2]]
     for x in range(_BS)]
    for y in range(_BS)
]

EXACT = 0
LOWER = 1
UPPER = 2
TT_MAX = 1_000_000

_TT: dict = {}
_start_time: float = 0.0
_time_up: bool = False


# ──────────────────────────────────────────────────────────
# 棋盤讀取
# ──────────────────────────────────────────────────────────
def read_board(stream, size: int):
    line = stream.readline().strip()
    if line != "BOARD":
        raise ValueError(f"expected BOARD, got: {line!r}")
    board = []
    for _ in range(size):
        row = list(map(int, stream.readline().split()))
        if len(row) != size:
            raise ValueError("invalid row length")
        board.append(row)
    line = stream.readline().strip()
    if line != "END_BOARD":
        raise ValueError(f"expected END_BOARD, got: {line!r}")
    return board


# ──────────────────────────────────────────────────────────
# 評分函式（增強版）
# ──────────────────────────────────────────────────────────
def segment_score(length: int, open_ends: int) -> int:
    if length >= 5: return 10_000_000
    if length == 4: return 2_000_000 if open_ends == 2 else 200_000
    if length == 3: return 50_000    if open_ends == 2 else 3_000
    if length == 2: return 500       if open_ends == 2 else 80
    if length == 1: return 15        if open_ends == 2 else 0
    return 0


def score_color(board, color: int) -> int:
    size = len(board)
    total = 0
    for y in range(size):
        for x in range(size):
            if board[y][x] != color:
                continue
            for dx, dy in DIRECTIONS:
                px, py = x - dx, y - dy
                if in_bounds(px, py, size) and board[py][px] == color:
                    continue
                length = 0
                cx, cy = x, y
                while in_bounds(cx, cy, size) and board[cy][cx] == color:
                    length += 1
                    cx += dx
                    cy += dy
                open_ends = 0
                if in_bounds(px, py, size) and board[py][px] == EMPTY:
                    open_ends += 1
                if in_bounds(cx, cy, size) and board[cy][cx] == EMPTY:
                    open_ends += 1
                total += segment_score(length, open_ends)
    return total


def evaluate(board, player: int) -> int:
    mine = score_color(board, player)
    opp  = score_color(board, opponent(player))
    return mine - int(opp * _current_opp_weight)


# ──────────────────────────────────────────────────────────
# 候選著法產生
# ──────────────────────────────────────────────────────────
def generate_candidate_moves(board, radius: int) -> list:
    size = len(board)
    if is_empty_board(board):
        c = size // 2
        return [(c, c)]
    moves: set = set()
    for y in range(size):
        for x in range(size):
            if board[y][x] == EMPTY:
                continue
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    nx, ny = x + dx, y + dy
                    if in_bounds(nx, ny, size) and board[ny][nx] == EMPTY:
                        moves.add((nx, ny))
    return list(moves)


def local_line_value(board, x: int, y: int, color: int) -> int:
    size = len(board)
    total = 0
    for dx, dy in DIRECTIONS:
        left = 0
        cx, cy = x - dx, y - dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color:
            left += 1
            cx -= dx
            cy -= dy
        right = 0
        cx, cy = x + dx, y + dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color:
            right += 1
            cx += dx
            cy += dy
        length = 1 + left + right
        lx, ly = x - (left + 1) * dx, y - (left + 1) * dy
        rx, ry = x + (right + 1) * dx, y + (right + 1) * dy
        open_ends = 0
        if in_bounds(lx, ly, size) and board[ly][lx] == EMPTY:
            open_ends += 1
        if in_bounds(rx, ry, size) and board[ry][rx] == EMPTY:
            open_ends += 1
        total += segment_score(length, open_ends)
    return total


def is_threat_move(board, x: int, y: int, color: int) -> bool:
    """判斷在 (x,y)（已放子）是否形成四連以上威脅"""
    size = len(board)
    for dx, dy in DIRECTIONS:
        left = 0
        cx, cy = x - dx, y - dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color:
            left += 1
            cx -= dx
            cy -= dy
        right = 0
        cx, cy = x + dx, y + dy
        while in_bounds(cx, cy, size) and board[cy][cx] == color:
            right += 1
            cx += dx
            cy += dy
        if 1 + left + right >= 4:
            return True
    return False


def get_threat_moves(board, player: int) -> list:
    """
    取得威脅著法：
    1. 自己可立即獲勝 → 只返回這個
    2. 自己的進攻四連
    3. 對手的立即勝著（必堵）
    4. 對手的四連（應堵）
    """
    opp = opponent(player)
    threats = []
    raw = generate_candidate_moves(board, NEIGHBOR_RADIUS)

    for x, y in raw:
        if not is_legal_move(board, x, y, player):
            continue

        board[y][x] = player
        if is_win_after_move(board, x, y, player):
            board[y][x] = EMPTY
            return [(x, y)]  # 立即勝，只返回此著
        atk_four = is_threat_move(board, x, y, player)
        board[y][x] = EMPTY

        board[y][x] = opp
        opp_win    = is_win_after_move(board, x, y, opp)
        opp_four   = is_threat_move(board, x, y, opp)
        board[y][x] = EMPTY

        if opp_win or atk_four or opp_four:
            threats.append((x, y))

    return threats


def move_priority(board, x: int, y: int, player: int) -> int:
    size   = len(board)
    center = size // 2
    opp    = opponent(player)

    board[y][x] = player
    self_win   = is_win_after_move(board, x, y, player)
    self_score = local_line_value(board, x, y, player)
    board[y][x] = EMPTY
    if self_win:
        return 10 ** 12

    board[y][x] = opp
    opp_win    = is_win_after_move(board, x, y, opp)
    block_score = local_line_value(board, x, y, opp)
    board[y][x] = EMPTY

    n1 = occupied_neighbors(board, x, y, radius=1)
    n2 = occupied_neighbors(board, x, y, radius=2)
    center_bonus = size - (abs(x - center) + abs(y - center))

    return (
        (10 ** 11 if opp_win else 0) +
        self_score  * 5 +
        block_score * 4 +
        n1 * 120 +
        n2 * 25 +
        center_bonus
    )


def ordered_moves(board, player: int) -> list:
    raw   = generate_candidate_moves(board, radius=NEIGHBOR_RADIUS)
    moves = [(x, y) for x, y in raw if is_legal_move(board, x, y, player)]
    if not moves:
        moves = legal_moves(board, player)
    scored = [(move_priority(board, x, y, player), x, y) for x, y in moves]
    scored.sort(reverse=True)
    return [(x, y) for _, x, y in scored[:MAX_CANDIDATES]]


# ──────────────────────────────────────────────────────────
# 靜止搜尋（Quiescence Search）
# ──────────────────────────────────────────────────────────
def quiescence(board, qdepth: int, alpha: int, beta: int, player: int) -> int:
    """
    當主搜尋 depth=0 時，繼續搜尋威脅著法，直到局面穩定。
    避免「水平線效應」：在搜尋截止點前最後一步有威脅但沒看到。
    """
    global _time_up
    if _time_up:
        return 0
    if time.perf_counter() - _start_time > TIME_BUDGET:
        _time_up = True
        return 0

    stand_pat = evaluate(board, player)
    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat
    if qdepth <= 0:
        return stand_pat

    threat_moves = get_threat_moves(board, player)
    if not threat_moves:
        return stand_pat

    opp = opponent(player)
    for x, y in threat_moves:
        board[y][x] = player
        if is_win_after_move(board, x, y, player):
            board[y][x] = EMPTY
            return WIN_SCORE
        val = -quiescence(board, qdepth - 1, -beta, -alpha, opp)
        board[y][x] = EMPTY
        if _time_up:
            return alpha
        if val >= beta:
            return beta
        if val > alpha:
            alpha = val

    return alpha


# ──────────────────────────────────────────────────────────
# PVS + Alpha-Beta + 轉置表 + 靜止搜尋
# ──────────────────────────────────────────────────────────
def pvs(board, depth: int, alpha: int, beta: int, player: int,
        zh: int, root_depth: int) -> int:
    """
    Principal Variation Search (PVS / NegaScout):
    - 第一個著法（排序後最佳）用完整窗口 [alpha, beta]
    - 後續著法先用零窗口 [alpha, alpha+1] 驗證
    - 若零窗口未截斷且可能改善 alpha，重新用完整窗口搜尋
    - depth=0 時進入靜止搜尋（非直接估分）
    """
    global _time_up

    if _time_up:
        return 0
    if time.perf_counter() - _start_time > TIME_BUDGET:
        _time_up = True
        return 0
    if board_full(board):
        return 0

    # depth=0 進入靜止搜尋（而非直接估分）
    if depth == 0:
        return quiescence(board, QSEARCH_DEPTH, alpha, beta, player)

    # 轉置表查找
    tt_entry = _TT.get(zh)
    if tt_entry is not None:
        ts, td, tf = tt_entry
        if td >= depth:
            if tf == EXACT:
                return ts
            if tf == LOWER and ts > alpha:
                alpha = ts
            elif tf == UPPER and ts < beta:
                beta = ts
            if alpha >= beta:
                return ts

    moves = ordered_moves(board, player)
    if not moves:
        return 0

    best       = -INF
    orig_alpha = alpha
    opp        = opponent(player)
    first      = True

    for x, y in moves:
        new_zh = zh ^ ZOBRIST[y][x][player]
        board[y][x] = player
        if is_win_after_move(board, x, y, player):
            val = WIN_SCORE - (root_depth - depth)
        elif first:
            # PV 節點：完整窗口搜尋
            val = -pvs(board, depth - 1, -beta, -alpha, opp, new_zh, root_depth)
            first = False
        else:
            # 非 PV 節點：零窗口測試
            val = -pvs(board, depth - 1, -alpha - 1, -alpha, opp, new_zh, root_depth)
            # 若可能改善 alpha 且未被截斷，重新完整搜尋
            if not _time_up and alpha < val < beta:
                val = -pvs(board, depth - 1, -beta, -alpha, opp, new_zh, root_depth)
        board[y][x] = EMPTY

        if _time_up:
            return best if best > -INF else 0

        if val > best:
            best = val
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break

    if not _time_up and len(_TT) < TT_MAX:
        if best <= orig_alpha:
            flag = UPPER
        elif best >= beta:
            flag = LOWER
        else:
            flag = EXACT
        _TT[zh] = (best, depth, flag)

    return best


def init_zobrist_hash(board) -> int:
    h = 0
    for y, row in enumerate(board):
        for x, c in enumerate(row):
            h ^= ZOBRIST[y][x][c]
    return h


# ──────────────────────────────────────────────────────────
# 主選手函式（IDDFS + PVS）
# ──────────────────────────────────────────────────────────
def choose_move(board, my_color: int):
    global _start_time, _time_up, _TT, _current_opp_weight
    _start_time = time.perf_counter()
    _time_up    = False
    _TT         = {}

    # 計算全盤棋子數以動態調整防守權重
    total_pieces = sum(1 for row in board for c in row if c != EMPTY)
    if total_pieces < 15:
        _current_opp_weight = 1.1
    elif total_pieces <= 40:
        _current_opp_weight = 1.3
    else:
        _current_opp_weight = 1.5

    size = len(board)
    if is_empty_board(board):
        c = size // 2
        return c, c

    zh  = init_zobrist_hash(board)
    opp = opponent(my_color)
    best_move = None

    for depth in range(1, MAX_DEPTH + 1):
        if time.perf_counter() - _start_time > TIME_BUDGET:
            break

        moves = ordered_moves(board, my_color)
        if not moves:
            break

        best_score = -INF
        candidate  = moves[0]
        alpha, beta = -INF, INF
        first = True

        for x, y in moves:
            new_zh = zh ^ ZOBRIST[y][x][my_color]
            board[y][x] = my_color
            if is_win_after_move(board, x, y, my_color):
                score = WIN_SCORE
            elif first:
                score = -pvs(board, depth - 1, -beta, -alpha, opp, new_zh, depth)
                first = False
            else:
                score = -pvs(board, depth - 1, -alpha - 1, -alpha, opp, new_zh, depth)
                if not _time_up and alpha < score < beta:
                    score = -pvs(board, depth - 1, -beta, -alpha, opp, new_zh, depth)
            board[y][x] = EMPTY

            if _time_up:
                break

            if score > best_score:
                best_score = score
                candidate  = (x, y)
            if score > alpha:
                alpha = score

        if not _time_up:
            best_move = candidate
            if best_score >= WIN_SCORE - MAX_DEPTH:
                break

    if best_move is None:
        fallback = legal_moves(board, my_color)
        if not fallback:
            raise RuntimeError("no legal moves")
        return fallback[0]

    return best_move


# ──────────────────────────────────────────────────────────
# 主程式（I/O 協定）
# ──────────────────────────────────────────────────────────
def main():
    board_size = None
    my_color   = None

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        parts = line.split()

        if parts[0] == "START":
            board_size = int(parts[1])
            role       = parts[2].upper()
            my_color   = BLACK if role == "BLACK" else WHITE

        elif parts[0] == "TURN":
            if board_size is None or my_color is None:
                raise RuntimeError("engine not initialized")
            board = read_board(sys.stdin, board_size)
            x, y = choose_move(board, my_color)
            print(f"MOVE {x} {y}", flush=True)

        elif parts[0] == "END":
            break


if __name__ == "__main__":
    main()
