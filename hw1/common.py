EMPTY = 0
BLACK = 1
WHITE = 2

STONE_TO_CHAR = {
    EMPTY: ".",
    BLACK: "X",
    WHITE: "O",
}

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]


def opponent(color: int) -> int:
    return WHITE if color == BLACK else BLACK


def create_board(size: int):
    return [[EMPTY for _ in range(size)] for _ in range(size)]


def in_bounds(x: int, y: int, size: int) -> bool:
    return 0 <= x < size and 0 <= y < size


def board_full(board) -> bool:
    return all(cell != EMPTY for row in board for cell in row)


def count_dir(board, x: int, y: int, dx: int, dy: int, color: int) -> int:
    size = len(board)
    cnt = 0
    cx, cy = x + dx, y + dy
    while in_bounds(cx, cy, size) and board[cy][cx] == color:
        cnt += 1
        cx += dx
        cy += dy
    return cnt


def line_total(board, x: int, y: int, dx: int, dy: int, color: int) -> int:
    return 1 + count_dir(board, x, y, dx, dy, color) + count_dir(board, x, y, -dx, -dy, color)


def is_overline_after_move(board, x: int, y: int, color: int) -> bool:
    for dx, dy in DIRECTIONS:
        if line_total(board, x, y, dx, dy, color) >= 6:
            return True
    return False


def is_exact_five_after_move(board, x: int, y: int, color: int) -> bool:
    for dx, dy in DIRECTIONS:
        if line_total(board, x, y, dx, dy, color) == 5:
            return True
    return False


def is_win_after_move(board, x: int, y: int, color: int) -> bool:
    if color == BLACK:
        return is_exact_five_after_move(board, x, y, BLACK) and not is_overline_after_move(board, x, y, BLACK)
    else:
        for dx, dy in DIRECTIONS:
            if line_total(board, x, y, dx, dy, WHITE) >= 5:
                return True
        return False


def is_open_four_in_direction(board, x: int, y: int, color: int, dx: int, dy: int) -> bool:
    size = len(board)
    left = count_dir(board, x, y, -dx, -dy, color)
    right = count_dir(board, x, y, dx, dy, color)
    total = 1 + left + right
    if total != 4:
        return False

    lx = x - (left + 1) * dx
    ly = y - (left + 1) * dy
    rx = x + (right + 1) * dx
    ry = y + (right + 1) * dy

    left_open = in_bounds(lx, ly, size) and board[ly][lx] == EMPTY
    right_open = in_bounds(rx, ry, size) and board[ry][rx] == EMPTY
    return left_open and right_open


def has_four_in_direction_for_black(board, x: int, y: int, dx: int, dy: int) -> bool:
    size = len(board)
    for k in range(-4, 5):
        nx = x + k * dx
        ny = y + k * dy
        if not in_bounds(nx, ny, size):
            continue
        if board[ny][nx] != EMPTY:
            continue

        board[ny][nx] = BLACK
        ok = is_win_after_move(board, nx, ny, BLACK)
        board[ny][nx] = EMPTY

        if ok:
            return True

    return False


def has_open_three_in_direction_for_black(board, x: int, y: int, dx: int, dy: int) -> bool:
    size = len(board)
    for k in range(-4, 5):
        nx = x + k * dx
        ny = y + k * dy
        if not in_bounds(nx, ny, size):
            continue
        if board[ny][nx] != EMPTY:
            continue

        board[ny][nx] = BLACK
        ok = (not is_overline_after_move(board, nx, ny, BLACK)) and is_open_four_in_direction(board, nx, ny, BLACK, dx, dy)
        board[ny][nx] = EMPTY

        if ok:
            return True

    return False


def count_black_four_directions(board, x: int, y: int) -> int:
    cnt = 0
    for dx, dy in DIRECTIONS:
        if has_four_in_direction_for_black(board, x, y, dx, dy):
            cnt += 1
    return cnt


def count_black_open_three_directions(board, x: int, y: int) -> int:
    cnt = 0
    for dx, dy in DIRECTIONS:
        if has_open_three_in_direction_for_black(board, x, y, dx, dy):
            cnt += 1
    return cnt


def is_black_forbidden_after_move(board, x: int, y: int) -> bool:
    if board[y][x] != BLACK:
        return False

    if is_overline_after_move(board, x, y, BLACK):
        return True

    if is_exact_five_after_move(board, x, y, BLACK):
        return False

    if count_black_four_directions(board, x, y) >= 2:
        return True

    if count_black_open_three_directions(board, x, y) >= 2:
        return True

    return False


def is_legal_move(board, x: int, y: int, color: int) -> bool:
    size = len(board)
    if not in_bounds(x, y, size):
        return False
    if board[y][x] != EMPTY:
        return False

    board[y][x] = color
    illegal = (color == BLACK and is_black_forbidden_after_move(board, x, y))
    board[y][x] = EMPTY
    return not illegal


def legal_moves(board, color: int):
    size = len(board)
    moves = []
    for y in range(size):
        for x in range(size):
            if board[y][x] == EMPTY and is_legal_move(board, x, y, color):
                moves.append((x, y))
    return moves


def format_board(board) -> str:
    size = len(board)
    lines = []
    header = "   " + " ".join(f"{x:>2}" for x in range(size))
    lines.append(header)
    for y in range(size):
        row_str = " ".join(f"{STONE_TO_CHAR[board[y][x]]:>2}" for x in range(size))
        lines.append(f"{y:>2} {row_str}")
    return "\n".join(lines)


def occupied_neighbors(board, x: int, y: int, radius: int = 1) -> int:
    size = len(board)
    cnt = 0
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if in_bounds(nx, ny, size) and board[ny][nx] != EMPTY:
                cnt += 1
    return cnt


def is_empty_board(board) -> bool:
    return all(cell == EMPTY for row in board for cell in row)
