import sys
import argparse
from pathlib import Path

# 讓 engine 在任何工作目錄下執行時，都能找到同資料夾的 common.py。
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from common import (
    EMPTY, BLACK, WHITE,
    opponent, in_bounds, board_full,
    occupied_neighbors, is_empty_board,
    is_legal_move, legal_moves, is_win_after_move,
)

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]
WIN_SCORE = 100_000_000
INF = 10**18


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", type=int, default=2, help="minimax search depth")
    parser.add_argument("--max-candidates", type=int, default=12, help="candidate move cap")
    parser.add_argument("--neighbor-radius", type=int, default=2, help="generate moves near existing stones")
    return parser.parse_args()


ARGS = parse_args()


def read_board_from_stream(stream, size: int):
    line = stream.readline()
    if not line:
        raise EOFError("unexpected EOF while waiting for BOARD")
    if line.strip() != "BOARD":
        raise ValueError(f"expected BOARD, got: {line.strip()}")

    board = []
    for _ in range(size):
        row_line = stream.readline()
        if not row_line:
            raise EOFError("unexpected EOF while reading board rows")
        row = list(map(int, row_line.strip().split()))
        if len(row) != size:
            raise ValueError(f"invalid board row length: {len(row)} != {size}")
        board.append(row)

    end_line = stream.readline()
    if not end_line:
        raise EOFError("unexpected EOF while waiting for END_BOARD")
    if end_line.strip() != "END_BOARD":
        raise ValueError(f"expected END_BOARD, got: {end_line.strip()}")

    return board


def count_run(board, x: int, y: int, dx: int, dy: int, color: int) -> int:
    size = len(board)
    cnt = 0
    cx, cy = x + dx, y + dy
    while in_bounds(cx, cy, size) and board[cy][cx] == color:
        cnt += 1
        cx += dx
        cy += dy
    return cnt


def segment_score(length: int, open_ends: int) -> int:
    if length >= 5:
        return 10_000_000
    if length == 4:
        if open_ends == 2:
            return 1_000_000
        if open_ends == 1:
            return 100_000
    elif length == 3:
        if open_ends == 2:
            return 10_000
        if open_ends == 1:
            return 1_000
    elif length == 2:
        if open_ends == 2:
            return 300
        if open_ends == 1:
            return 50
    elif length == 1:
        if open_ends == 2:
            return 10
    return 0


def local_line_value(board, x: int, y: int, color: int) -> int:
    size = len(board)
    total = 0

    for dx, dy in DIRECTIONS:
        left = count_run(board, x, y, -dx, -dy, color)
        right = count_run(board, x, y, dx, dy, color)
        length = 1 + left + right

        lx = x - (left + 1) * dx
        ly = y - (left + 1) * dy
        rx = x + (right + 1) * dx
        ry = y + (right + 1) * dy

        open_ends = 0
        if in_bounds(lx, ly, size) and board[ly][lx] == EMPTY:
            open_ends += 1
        if in_bounds(rx, ry, size) and board[ry][rx] == EMPTY:
            open_ends += 1

        total += segment_score(length, open_ends)

    return total


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
    opp = score_color(board, opponent(player))
    return mine - int(opp * 1.1)


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


def is_immediate_winning_move(board, x: int, y: int, color: int) -> bool:
    if not is_legal_move(board, x, y, color):
        return False
    board[y][x] = color
    won = is_win_after_move(board, x, y, color)
    board[y][x] = EMPTY
    return won



def move_priority(board, x: int, y: int, player: int) -> int:
    size = len(board)
    center = size // 2
    opp = opponent(player)

    # 非法著法不應進入排序，但仍加保險。
    if not is_legal_move(board, x, y, player):
        return -INF

    # 自己下了就直接贏
    board[y][x] = player
    self_win = is_win_after_move(board, x, y, player)
    self_score = local_line_value(board, x, y, player)
    board[y][x] = EMPTY
    if self_win:
        return 10**12

    # 這格是否是對手的合法立即致勝點（可用來堵）
    opp_can_win = is_immediate_winning_move(board, x, y, opp)
    board[y][x] = opp
    block_score = local_line_value(board, x, y, opp)
    board[y][x] = EMPTY

    n1 = occupied_neighbors(board, x, y, radius=1)
    n2 = occupied_neighbors(board, x, y, radius=2)
    center_bonus = size - (abs(x - center) + abs(y - center))

    return (
        (10**11 if opp_can_win else 0) +
        self_score * 4 +
        block_score * 3 +
        n1 * 100 +
        n2 * 20 +
        center_bonus
    )


def ordered_moves(board, player: int, max_candidates: int, radius: int):
    raw_moves = generate_candidate_moves(board, radius=radius)
    moves = [(x, y) for x, y in raw_moves if is_legal_move(board, x, y, player)]

    if not moves:
        moves = legal_moves(board, player)

    scored = []
    for x, y in moves:
        scored.append((move_priority(board, x, y, player), x, y))
    scored.sort(reverse=True)
    return [(x, y) for _, x, y in scored[:max_candidates]]


def negamax(board, depth: int, alpha: int, beta: int, player: int,
            max_candidates: int, radius: int) -> int:
    if board_full(board):
        return 0

    if depth == 0:
        return evaluate(board, player)

    moves = ordered_moves(board, player, max_candidates=max_candidates, radius=radius)
    if not moves:
        return 0

    best = -INF
    opp = opponent(player)

    for x, y in moves:
        board[y][x] = player

        if is_win_after_move(board, x, y, player):
            val = WIN_SCORE - (ARGS.depth - depth)
        else:
            val = -negamax(board, depth - 1, -beta, -alpha, opp,
                           max_candidates=max_candidates, radius=radius)

        board[y][x] = EMPTY

        if val > best:
            best = val
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break

    return best


def choose_move(board, my_color: int, depth: int, max_candidates: int, radius: int):
    size = len(board)
    if is_empty_board(board):
        c = size // 2
        return c, c

    moves = ordered_moves(board, my_color, max_candidates=max_candidates, radius=radius)
    if not moves:
        legal_now = legal_moves(board, my_color)
        if not legal_now:
            raise RuntimeError("no legal moves available")
        return legal_now[0]

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
            score = -negamax(
                board, depth - 1, -beta, -alpha, opp,
                max_candidates=max_candidates, radius=radius
            )

        board[y][x] = EMPTY

        if score > best_score:
            best_score = score
            best_move = (x, y)

        if score > alpha:
            alpha = score

    return best_move


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
                raise RuntimeError("engine not initialized by START")

            board = read_board_from_stream(sys.stdin, board_size)
            x, y = choose_move(
                board, my_color,
                depth=ARGS.depth,
                max_candidates=ARGS.max_candidates,
                radius=ARGS.neighbor_radius
            )
            print(f"MOVE {x} {y}", flush=True)

        elif parts[0] == "END":
            break


if __name__ == "__main__":
    main()
