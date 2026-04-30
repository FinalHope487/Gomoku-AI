import os
import subprocess
import concurrent.futures
import time
import logging
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler("variants_benchmark_results.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def run_match(black_engine, white_engine):
    start_time = time.time()
    # To avoid the cp950 encoding error on Windows, we pass PYTHONIOENCODING='utf-8'
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    cmd = ["python", "hw1/referee.py", "--black", black_engine, "--white", white_engine]
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding='utf-8')
        output = result.stdout
        
        # Parse result
        if "BLACK wins" in output:
            winner = "BLACK"
        elif "WHITE wins" in output:
            winner = "WHITE"
        elif "Draw" in output or "DRAW" in output.upper():
            winner = "DRAW"
        else:
            winner = "UNKNOWN"
            
        b_times = [float(m) for m in re.findall(r"Move \d+: BLACK -> \S+\s+\[([\d.]+)s\]", output)]
        w_times = [float(m) for m in re.findall(r"Move \d+: WHITE -> \S+\s+\[([\d.]+)s\]", output)]
        
        def get_stats(times):
            if not times: return "0.000", "0.000", "0.000"
            return f"{min(times):.3f}", f"{(sum(times)/len(times)):.3f}", f"{max(times):.3f}"
            
        b_min, b_avg, b_max = get_stats(b_times)
        w_min, w_avg, w_max = get_stats(w_times)
            
        elapsed = time.time() - start_time
        return {
            "black": black_engine,
            "white": white_engine,
            "winner": winner,
            "time": elapsed,
            "b_stats": (b_min, b_avg, b_max),
            "w_stats": (w_min, w_avg, w_max),
            "status": "success",
            "error": result.stderr
        }
    except Exception as e:
        return {
            "black": black_engine,
            "white": white_engine,
            "winner": "ERROR",
            "time": 0,
            "status": "error",
            "error": str(e)
        }

def main():
    # Opponents
    black_engines = [
        "hw1/engine_minimax.py",
        "hw1/engine_black2_var1.py",
        "hw1/engine_black3_var2.py",
        "hw1/engine_black4_aggro.py"
    ]
    # Variants to test
    white_engines = [
        "hw1_11427234_v24.py",
        "hw1_11427234_v24-1.py",
        "hw1_11427234_v24-2.py",
        "hw1_11427234_v25.py",
        "hw1_11427234_v25-1.py",
        "hw1_11427234_v25-2.py"
    ]
    
    # Check if files exist
    for engine in set(black_engines + white_engines):
        if not os.path.exists(engine):
            logging.error(f"Engine file not found: {engine}")
            return
            
    matches = [(b, w) for b in black_engines for w in white_engines]
    total_matches = len(matches)
    
    logging.info(f"Starting benchmark for {total_matches} matches...")
    
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
        future_to_match = {executor.submit(run_match, b, w): (b, w) for b, w in matches}
        
        completed = 0
        for future in concurrent.futures.as_completed(future_to_match):
            b, w = future_to_match[future]
            try:
                data = future.result()
                results.append(data)
                completed += 1
                if data["status"] == "success":
                    msg = (f"Match {completed}/{total_matches} | Black: {b} vs White: {w} | Winner: {data['winner']} | Total Time: {data['time']:.2f}s\n"
                           f"    Black Avg Time: {data['b_stats'][1]}s | White Avg Time: {data['w_stats'][1]}s")
                    logging.info(msg)
                else:
                    msg = f"Match {completed}/{total_matches} | Black: {b} vs White: {w} | ERROR: {data['error']}"
                    logging.error(msg)
            except Exception as exc:
                logging.error(f"Match {b} vs {w} generated an exception: {exc}")

    # Summary report generation (internal)
    logging.info("="*40)
    logging.info("BENCHMARK SUMMARY")
    logging.info("="*40)
    
    for w in white_engines:
        variant_results = [r for r in results if r['white'] == w]
        wins = sum(1 for r in variant_results if r['winner'] == 'WHITE')
        losses = sum(1 for r in variant_results if r['winner'] == 'BLACK')
        draws = sum(1 for r in variant_results if r['winner'] == 'DRAW')
        avg_time = sum(float(r['w_stats'][1]) for r in variant_results if r['status'] == 'success') / len(variant_results) if variant_results else 0
        logging.info(f"Variant {w}: Wins: {wins}, Losses: {losses}, Draws: {draws}, Avg Move Time: {avg_time:.3f}s")

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
