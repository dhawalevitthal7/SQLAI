import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend BEFORE importing pyplot
import matplotlib.pyplot as plt
import seaborn as sns
import base64
import glob
import tempfile
import io

class VizService:
    @staticmethod
    def safe_exec_globals():
        def forbidden_op(*args, **kwargs):
            raise ValueError("EXEC SECURITY: This operation (exit/quit) is forbidden.")
        
        return {
            "pd": pd, 
            "plt": plt, 
            "sns": sns,
            "exit": forbidden_op,
            "quit": forbidden_op,
            "print": print
        }

    @staticmethod
    def generate_visualizations(df: pd.DataFrame, query: str, ai_service, temp_dir: str) -> list:
        # Ensure Agg backend is active (safety net for worker threads)
        matplotlib.use('Agg')
        plt.switch_backend('Agg')
        
        csv_path = os.path.join(temp_dir, "data.csv")
        df.to_csv(csv_path, index=False)
        
        # Provide sample rows so AI can see actual data formats
        sample_rows = df.head(3).to_string(index=False)
        dtypes_info = df.dtypes.to_string()
        
        viz_prompt = f"""
        Visualize this data. Context: {query}. 
        Input CSV: '{csv_path}'. 
        Columns: {df.columns.tolist()}.
        Data Types:
        {dtypes_info}
        Sample Data (first 3 rows):
        {sample_rows}
        
        Output: Save charts to '{temp_dir}' using plt.savefig(). 
        
        STRICT RULES:
        - NO plt.show(). NO exit(). NO quit().
        - Do NOT use infer_datetime_format parameter in pd.to_datetime().
        - For date parsing, use pd.to_datetime(col, format='mixed') or pd.to_datetime(col, format='ISO8601'). NEVER guess a manual format string.
        - Always use plt.tight_layout() before saving.
        - Use plt.figure() for each chart.
        """
        py_script = ai_service.gemini_call(viz_prompt, "Generate Viz Code")
        
        max_retries = 1
        attempts = 0
        graphs = []
        
        while attempts <= max_retries:
            try:
                plt.close('all')
                exec_globals = VizService.safe_exec_globals()
                exec(py_script, exec_globals)
                for img in glob.glob(os.path.join(temp_dir, "*.png")):
                    with open(img, "rb") as f:
                        graphs.append(base64.b64encode(f.read()).decode('utf-8'))
                break  # Success — exit the retry loop
            except Exception as e:
                attempts += 1
                if attempts <= max_retries:
                    print(f"🔄 Viz error on attempt {attempts}: {e}. Retrying with corrected script...")
                    # Clean up any partial/broken PNGs from the failed attempt
                    for stale_img in glob.glob(os.path.join(temp_dir, "*.png")):
                        try:
                            os.remove(stale_img)
                        except OSError:
                            pass
                    fix_prompt = f"""
                    The following Python visualization script failed with an error.
                    Fix the script and return ONLY the corrected Python code. No markdown.

                    Original Script:
                    {py_script}

                    Error:
                    {e}

                    STRICT RULES:
                    - Save output to '{temp_dir}' using plt.savefig().
                    - NO plt.show(). NO exit(). NO quit().
                    - Do NOT use infer_datetime_format parameter in pd.to_datetime().
                    - For date parsing, use pd.to_datetime(col, format='mixed') or pd.to_datetime(col, format='ISO8601'). NEVER guess a manual format string.
                    - Input CSV is at '{csv_path}' with columns: {df.columns.tolist()}.
                    - Sample data:
                    {sample_rows}
                    """
                    py_script = ai_service.gemini_call(fix_prompt, "Fix Viz Code")
                    if not py_script:
                        print("❌ AI failed to generate corrected viz script.")
                        break
                else:
                    print(f"❌ Viz generation failed after {max_retries + 1} attempts: {e}")
            finally:
                plt.close('all')
        
        return graphs

