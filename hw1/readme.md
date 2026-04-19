# Gomoku 作業說明：`hw1_學號.py`（白子棋手程式）

## 1. 作業目標

請撰寫一個 Python 程式 `hw1_學號.py`，作為 **白子方** 的五子棋棋手。  
黑子方我們提供 `engine_minimax.py` 作為簡單參考對手(實際評分用的黑子程式不公布、且會比較強一點)；你的 `hw1_學號.py` 需要能與裁判程式透過 **stdin / stdout** 溝通，自動完成對弈。

棋盤大小固定為 **15 × 15**。

---

## 2. 你需要提交的檔案

請提交：

```text
hw1_學號.py (e.g.hw1_11227100.py)

```

檔名必須正確。評測時，助教會把你的 `hw1_學號.py` 當作白子方啟動。

---

## 3. 程式執行方式

你的程式會被裁判程式以 subprocess 方式啟動，並透過標準輸入 / 輸出交換訊息。  
因此你的 `hw1_學號.py` 必須：

1. 從 `stdin` 讀取裁判送來的指令。
2. 在輪到你下棋時，輸出一行：
   ```text
   MOVE x y
   ```
3. 每次輸出後務必 `flush=True`。

---

## 4. 通訊協定（I/O 規則）

你的 `hw1_學號.py` 需要處理以下三種指令：

### (A) `START`

裁判在對局開始時會送：

```text
START 15 WHITE
```

一般格式為：

```text
START <board_size> <role>
```

其中：
- `board_size`：棋盤大小，本作業固定為 15
- `role`：你的顏色方。對 `hw1_學號.py` 而言，評測時固定會是 `WHITE`

---

### (B) `TURN`

當輪到你下棋時，裁判會送：

```text
TURN
BOARD
<第 0 列 15 個整數>
<第 1 列 15 個整數>
...
<第 14 列 15 個整數>
END_BOARD
```

盤面上的整數編碼為：
- `0`：空格
- `1`：黑子
- `2`：白子

你的程式收到這段資料後，必須回傳：

```text
MOVE x y
```

---

### (C) `END`

當對局結束時，裁判會送出：

```text
END WIN
```

或

```text
END LOSE
```

或

```text
END DRAW
```

你的程式收到 `END` 後，直接結束即可。

---

## 5. 座標格式

你輸出的落子格式為：

```text
MOVE x y
```

其中：
- `x`：欄座標，由左至右範圍 `0 ~ 14`
- `y`：列座標，由上至下範圍 `0 ~ 14`

這裡採用 **0-based index**。  
例如：
- 左上角是 `MOVE 0 0`
- 棋盤中心是 `MOVE 7 7`

---

## 6. 合法落子規則

你的程式輸出的 `MOVE x y` 必須是合法著，否則會被判負。

基本合法條件：
1. 座標必須在棋盤內。
2. 該位置必須為空格。

---

## 7. 白子不需考慮禁手

本作業你寫的是 **白子方 `hw1_學號.py`**，因此 **不需要考慮黑棋禁手規則**（例如三三、四四、長連禁手）。

也就是說，對白棋而言，只要：
- 落點在棋盤內
- 該格為空

即可視為合法。

另外，勝利條件也請注意：
- **黑棋**：必須剛好五連，且不能長連
- **白棋**：五連以上即可獲勝

因此你在設計 `hw.py` 時，只需要專注於白棋策略，不必實作黑棋禁手判斷。

---

## 8. 時間限制

每一步落子時間上限為 **5 秒**。

若你的程式超時：
- 裁判會視為 timeout
- 若當下仍有合法著，裁判會隨機替你補下一個合法著
- 這會影響你的對局品質與最終得分

因此建議你的 `hw.py`：
- 盡量在 5 秒內完成落子
- 最好保留安全餘裕，例如控制在 4 秒內

---

## 9. 禁止事項

### (1) 不可使用 `random` 或其他隨機策略

本作業要求你的 `hw1_學號.py` 必須是 **確定性** 程式，**不可引用 `random` 模組**，也不可用亂數選步。  
同一個盤面輸入，應該產生同樣的輸出。

### (2) 不可輸出多餘訊息到 stdout

裁判只接受：

```text
MOVE x y
```

若你在 stdout 額外輸出 debug 訊息、提示文字或其他內容，可能導致裁判解析失敗。

如需除錯，請改輸出到 `stderr`，或自行在本機測試時使用。

---

## 10. 白子計分方式

本作業以 **白子成績** 為主要參考，白子的分數計算方式如下：

### 白棋獲勝下越早越好(224分~117分)

```text
234 - 白棋手數 - 白棋平均每步時間(四捨五入到 0.1 秒)
```

### 和局(117分~112分)

```text
117 - 白棋平均每步時間(四捨五入到 0.1 秒)
```

### 白棋落敗下越晚越好(112分~0分)

```text
白棋手數 - 白棋平均每步時間(四捨五入到 0.1 秒)
```

因此，一個好的 `hw1_學號.py` 不只要避免輸棋，也要盡量：
- 贏得更快
- 平均思考時間更短

---

## 11. 對局結束條件

對局可能因以下原因結束：

1. 某方形成勝利條件
2. 棋盤下滿，判和局
3. 某方輸出非法著
4. 某方發生 protocol / runtime error
5. 某方超時且後續被判負

---

## 12. 建議的 `hw.py` 主程式架構

你可以使用下列基本架構作為起點：

```python
import sys


def read_board(stream, size):
    line = stream.readline().strip()
    if line != "BOARD":
        raise ValueError("expected BOARD")

    board = []
    for _ in range(size):
        row = list(map(int, stream.readline().split()))
        if len(row) != size:
            raise ValueError("invalid row length")
        board.append(row)

    line = stream.readline().strip()
    if line != "END_BOARD":
        raise ValueError("expected END_BOARD")

    return board


def choose_move(board):
    # 請在此實作你的白棋策略
    # 回傳 (x, y)
    return 7, 7


def main():
    board_size = None
    my_role = None

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue

        parts = line.split()

        if parts[0] == "START":
            board_size = int(parts[1])
            my_role = parts[2]

        elif parts[0] == "TURN":
            board = read_board(sys.stdin, board_size)
            x, y = choose_move(board)
            print(f"MOVE {x} {y}", flush=True)

        elif parts[0] == "END":
            break


if __name__ == "__main__":
    main()
```

---

## 13. I/O 範例

### 輸入

```text
START 15 WHITE
TURN
BOARD
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 1 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
END_BOARD
```

### 輸出

```text
MOVE 7 8
```

---

## 14. 實作建議

你可以自由設計白棋策略，例如：
- 先檢查自己是否有立即勝著
- 若無，先堵住黑棋可能的連線
- 對候選著法做簡單評分
- 使用 minimax / negamax / alpha-beta pruning
- 或自行設計更有效率的方法

但請注意以下原則：
- 不可使用 `random`
- 不需考慮黑棋禁手實作
- 需符合裁判 I/O 規則
- 需在 5 秒內穩定輸出落子

---

## 15. 總結

你的 `hw1_學號.py` 必須做到：

1. 正確讀取裁判送來的 `START`、`TURN`、`END`
2. 在 `TURN` 時根據盤面輸出合法的 `MOVE x y`
3. 不使用隨機函式
4. 不需處理禁手
5. 儘量提升白子的最終分數

祝你實作順利。
