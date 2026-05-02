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
        logging.FileHandler("benchmark_results.log", encoding='utf-8'),
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
            if not times: return "N/A", "N/A", "N/A"
            return f"{min(times):.3f}", f"{(sum(times)/len(times)):.3f}", f"{max(times):.3f}"
            
        b_min, b_avg, b_max = get_stats(b_times)
        w_min, w_avg, w_max = get_stats(w_times)
            
        score_match = re.search(r"WHITE score: ([\d.]+)", output)
        white_score = score_match.group(1) if score_match else "N/A"
            
        elapsed = time.time() - start_time
        return {
            "black": black_engine,
            "white": white_engine,
            "winner": winner,
            "time": elapsed,
            "b_stats": (b_min, b_avg, b_max),
            "w_stats": (w_min, w_avg, w_max),
            "white_score": white_score,
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
    # Define your engines here.
    black_engines = [
        "hw1/engine_minimax.py",
        "hw1/engine_black2_var1.py",
        "hw1/engine_black3_var2.py",
        "hw1/engine_black4_aggro.py"
    ]
    white_engines = [
        "hw1_11427234_v9.py",
        "hw1_11427234_v20.py"
    ]
    
    # Check if files exist
    for engine in set(black_engines + white_engines):
        if not os.path.exists(engine):
            logging.error(f"Engine file not found: {engine}")
            return
            
    # Each different pairing only tests 1 time
    matches = [(b, w) for b in list(dict.fromkeys(black_engines)) for w in list(dict.fromkeys(white_engines))]
    total_matches = len(matches)
    
    logging.info(f"Starting benchmark for {total_matches} matches using multiprocessing...")
    
    results = []
    # Use max_workers=None to let it automatically choose the number of processors
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
                    msg = (f"Match {completed}/{total_matches} | Black: {b} vs White: {w} | Winner: {data['winner']} | Score: {data['white_score']} | Time: {data['time']:.2f}s\n"
                           f"    Black Min/Avg/Max: {data['b_stats'][0]}/{data['b_stats'][1]}/{data['b_stats'][2]}s\n"
                           f"    White Min/Avg/Max: {data['w_stats'][0]}/{data['w_stats'][1]}/{data['w_stats'][2]}s")
                    logging.info(msg)
                else:
                    msg = f"Match {completed}/{total_matches} | Black: {b} vs White: {w} | ERROR: {data['error']}"
                    logging.error(msg)
            except Exception as exc:
                logging.error(f"Match {b} vs {w} generated an exception: {exc}")

    # Summary
    logging.info("="*40)
    logging.info("BENCHMARK SUMMARY")
    logging.info("="*40)
    
    # Per-engine statistics
    white_stats = {}
    for r in results:
        w = r['white']
        if w not in white_stats:
            white_stats[w] = {'wins': 0, 'losses': 0, 'draws': 0, 'scores': [], 'matches': 0}
        
        white_stats[w]['matches'] += 1
        if r['winner'] == 'WHITE':
            white_stats[w]['wins'] += 1
        elif r['winner'] == 'BLACK':
            white_stats[w]['losses'] += 1
        elif r['winner'] == 'DRAW':
            white_stats[w]['draws'] += 1
            
        if r['status'] == 'success' and r['white_score'] != 'N/A':
            white_stats[w]['scores'].append(float(r['white_score']))

    black_wins = sum(1 for r in results if r['winner'] == 'BLACK')
    white_wins = sum(1 for r in results if r['winner'] == 'WHITE')
    draws = sum(1 for r in results if r['winner'] == 'DRAW')
    unknowns = sum(1 for r in results if r['winner'] == 'UNKNOWN')
    errors = sum(1 for r in results if r['status'] == 'error')

    logging.info(f"Total Matches: {total_matches}")
    logging.info(f"BLACK Wins: {black_wins}")
    logging.info(f"WHITE Wins: {white_wins}")
    logging.info(f"Draws: {draws}")
    if unknowns > 0:
        logging.info(f"Unknowns: {unknowns}")
    logging.info(f"Errors: {errors}")

    logging.info("="*40)
    logging.info("DETAILED WHITE ENGINE STATS")
    logging.info("="*40)
    for w, stats in white_stats.items():
        total_score = sum(stats['scores'])
        avg_score = total_score / len(stats['scores']) if stats['scores'] else 0.0
        logging.info(f"Engine: {w}")
        logging.info(f"  Matches: {stats['matches']} | Win/Loss: {stats['wins']}W/{stats['losses']}L/{stats['draws']}D")
        logging.info(f"  Total Score: {total_score:.1f} | Avg Score: {avg_score:.1f}")

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
