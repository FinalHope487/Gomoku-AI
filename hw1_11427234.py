import sys
from pathlib import Path

# 讓程式在任何工作目錄下都能找到 hw1/common.py
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
SEARCH_DEPTH = 3          # negamax 搜尋深度
MAX_CANDIDATES = 15       # 每層最多考慮幾個候選著
NEIGHBOR_RADIUS = 2       # 候選著法產生半徑

INF = 10 ** 18
WIN_SCORE = 100_000_000

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]


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
# 評分函式
# ──────────────────────────────────────────────────────────
def segment_score(length: int, open_ends: int) -> int:
    if length >= 5:
        return 10_000_000
    if length == 4:
        return 1_000_000 if open_ends == 2 else 100_000
    if length == 3:
        return 10_000 if open_ends == 2 else 1_000
    if length == 2:
        return 300 if open_ends == 2 else 50
    if length == 1:
        return 10 if open_ends == 2 else 0
    return 0


def score_color(board, color: int) -> int:
    size = len(board)
    total = 0
    for y in range(size):
        for x in range(size):
            if board[y][x] != color:
                continue
            for dx, dy in DIRECTIONS:
                # 只計算每個連線的起始端，避免重複計算
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
    return mine - int(opp * 1.1)


# ──────────────────────────────────────────────────────────
# 候選著法產生
# ──────────────────────────────────────────────────────────
def generate_candidate_moves(board, radius: int):
    size = len(board)
    if is_empty_board(board):
        c = size // 2
        return [(c, c)]
    moves = set()
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
    """快速計算在 (x,y) 放子後，該位置的連線得分（不修改棋盤）。"""
    size = len(board)
    total = 0
    for dx, dy in DIRECTIONS:
        # 向兩端延伸計算連續同色子數
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


def move_priority(board, x: int, y: int, player: int) -> int:
    size = len(board)
    center = size // 2
    opp = opponent(player)

    # 自己下了是否立即獲勝
    board[y][x] = player
    self_win = is_win_after_move(board, x, y, player)
    self_score = local_line_value(board, x, y, player)
    board[y][x] = EMPTY
    if self_win:
        return 10 ** 12

    # 對手下了是否立即獲勝（需要堵）
    board[y][x] = opp
    opp_win = is_win_after_move(board, x, y, opp)
    block_score = local_line_value(board, x, y, opp)
    board[y][x] = EMPTY

    n1 = occupied_neighbors(board, x, y, radius=1)
    n2 = occupied_neighbors(board, x, y, radius=2)
    center_bonus = size - (abs(x - center) + abs(y - center))

    return (
        (10 ** 11 if opp_win else 0) +
        self_score * 4 +
        block_score * 3 +
        n1 * 100 +
        n2 * 20 +
        center_bonus
    )


def ordered_moves(board, player: int, max_candidates: int, radius: int):
    raw = generate_candidate_moves(board, radius=radius)
    moves = [(x, y) for x, y in raw if is_legal_move(board, x, y, player)]
    if not moves:
        moves = legal_moves(board, player)

    scored = [(move_priority(board, x, y, player), x, y) for x, y in moves]
    scored.sort(reverse=True)
    return [(x, y) for _, x, y in scored[:max_candidates]]


# ──────────────────────────────────────────────────────────
# Negamax + Alpha-Beta 搜尋
# ──────────────────────────────────────────────────────────
def negamax(board, depth: int, alpha: int, beta: int, player: int) -> int:
    if board_full(board):
        return 0
    if depth == 0:
        return evaluate(board, player)

    moves = ordered_moves(board, player,
                          max_candidates=MAX_CANDIDATES,
                          radius=NEIGHBOR_RADIUS)
    if not moves:
        return 0

    best = -INF
    opp = opponent(player)

    for x, y in moves:
        board[y][x] = player
        if is_win_after_move(board, x, y, player):
            val = WIN_SCORE - (SEARCH_DEPTH - depth)
        else:
            val = -negamax(board, depth - 1, -beta, -alpha, opp)
        board[y][x] = EMPTY

        if val > best:
            best = val
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break

    return best


def choose_move(board, my_color: int):
    size = len(board)
    if is_empty_board(board):
        c = size // 2
        return c, c

    moves = ordered_moves(board, my_color,
                          max_candidates=MAX_CANDIDATES,
                          radius=NEIGHBOR_RADIUS)
    if not moves:
        fallback = legal_moves(board, my_color)
        if not fallback:
            raise RuntimeError("no legal moves")
        return fallback[0]

    best_score = -INF
    best_move = moves[0]
    alpha = -INF
    beta = INF
    opp = opponent(my_color)

    for x, y in moves:
        board[y][x] = my_color
        if is_win_after_move(board, x, y, my_color):
            score = WIN_SCORE
        else:
            score = -negamax(board, SEARCH_DEPTH - 1, -beta, -alpha, opp)
        board[y][x] = EMPTY

        if score > best_score:
            best_score = score
            best_move = (x, y)
        if score > alpha:
            alpha = score

    return best_move


# ──────────────────────────────────────────────────────────
# 主程式（I/O 協定）
# ──────────────────────────────────────────────────────────
def main():
    board_size = None
    my_color = None

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        parts = line.split()

        if parts[0] == "START":
            board_size = int(parts[1])
            role = parts[2].upper()
            my_color = BLACK if role == "BLACK" else WHITE

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
