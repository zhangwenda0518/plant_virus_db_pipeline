#!/usr/bin/env python3
"""
AutoPVPrimer - Automated Primer Design and Validation Pipeline

This script automates the process of downloading viral sequences,
creating consensus sequences, designing primers, and validating them.

Usage:
    python autopvprimer.py --virus "Tomato Mosaic Virus" --output /path/to/output
    python autopvprimer.py --fasta /path/to/sequences.fasta --output /path/to/output
    python autopvprimer.py --help
"""

import os
import time
import random
import shutil
import tempfile
import argparse
from collections import Counter

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from Bio import Entrez, SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.SeqUtils import MeltingTemp, gc_fraction
from Bio.Blast import NCBIWWW, NCBIXML

import primer3
from primer3 import calc_heterodimer

from sklearn.model_selection import RandomizedSearchCV
from sklearn.ensemble import RandomForestClassifier

# Set your NCBI email
Entrez.email = "ghorbani.abozar@gmail.com"

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="AutoPVPrimer - Automated Primer Design and Validation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download sequences from NCBI and design primers
  python autopvprimer.py --virus "Tomato Mosaic Virus" --output /path/to/output
  
  # Use existing FASTA file and design primers
  python autopvprimer.py --fasta /path/to/sequences.fasta --output /path/to/output
  
  # Use existing FASTA file with custom parameters
  python autopvprimer.py --fasta /path/to/sequences.fasta --output /path/to/output --num_primers 5
        """
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--virus", 
        help="Name of the virus to search for (e.g., 'Tomato Mosaic Virus')"
    )
    
    input_group.add_argument(
        "--fasta", 
        help="Path to existing FASTA file containing sequences"
    )
    
    # Required arguments
    parser.add_argument(
        "--output", 
        required=True,
        help="Output directory for results"
    )
    
    # Optional arguments
    parser.add_argument(
        "--email",
        default="ghorbani.abozar@gmail.com",
        help="Email address for NCBI queries (default: ghorbani.abozar@gmail.com)"
    )
    
    parser.add_argument(
        "--num_primers",
        type=int,
        default=3,
        help="Number of primer pairs to design (default: 3)"
    )
    
    parser.add_argument(
        "--product_size_min",
        type=int,
        default=250,
        help="Minimum product size for primers (default: 250)"
    )
    
    parser.add_argument(
        "--product_size_max",
        type=int,
        default=1000,
        help="Maximum product size for primers (default: 1000)"
    )
    
    parser.add_argument(
        "--tm_min",
        type=float,
        default=58.0,
        help="Minimum melting temperature for primers (default: 58.0)"
    )
    
    parser.add_argument(
        "--tm_max",
        type=float,
        default=64.0,
        help="Maximum melting temperature for primers (default: 64.0)"
    )
    
    parser.add_argument(
        "--skip_blast",
        action="store_true",
        help="Skip BLAST validation step (time-consuming)"
    )
    
    parser.add_argument(
        "--max_sequences",
        type=int,
        default=10,
        help="Maximum number of sequences to download (default: 10)"
    )
    
    parser.add_argument(
        "--skip_tuning",
        action="store_true",
        help="Skip primer tuning with machine learning"
    )
    
    return parser.parse_args()

def download_all_sequences(virus_name, save_path, max_sequences=10):
    """Download all genome sequences of the specified virus from NCBI nucleotide database."""
    try:
        # Search for all genome sequences of the specified virus in NCBI nucleotide database
        search_term = f"{virus_name}[Organism] AND genome[Title]"
        handle = Entrez.esearch(db="nucleotide", term=search_term, retmax=max_sequences,idtype="acc")
        record = Entrez.read(handle)
        handle.close()

        if record["Count"] == "0":
            print(f"No records found for {virus_name}. Please check the virus name.")
            return None

        # Create the save path if it doesn't exist
        if not os.path.exists(save_path):
            os.makedirs(save_path)

        # Fetch and save all sequences directly to the specified save path
        for seq_id in record["IdList"]:
            handle = Entrez.efetch(db="nucleotide", id=seq_id, rettype="fasta", retmode="text")
            seq_record = SeqIO.read(handle, "fasta")
            handle.close()

            # Save each sequence to the specified save path
            filename = f"{virus_name.replace(' ', '_')}_{seq_id}.fasta"
            filepath = os.path.join(save_path, filename)
            SeqIO.write(seq_record, filepath, "fasta")
            print(f"Sequence {seq_id} saved: {filepath}")

        print(f"All sequences downloaded and saved to {save_path}")
        return save_path

    except Entrez.EntrezError as e:
        print(f"NCBI error: {e}")
        return None
    except IOError as e:
        print(f"IO error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def process_fasta_file(fasta_path, output_path):
    """Process a single FASTA file (could contain multiple sequences)."""
    try:
        # Create the output directory if it doesn't exist
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            
        # Check if the input file exists
        if not os.path.exists(fasta_path):
            print(f"FASTA file not found: {fasta_path}")
            return None
            
        # Read all sequences from the FASTA file
        sequences = list(SeqIO.parse(fasta_path, "fasta"))
        
        if not sequences:
            print(f"No sequences found in {fasta_path}")
            return None
            
        print(f"Found {len(sequences)} sequences in {fasta_path}")
        
        # Save each sequence as a separate file
        for i, seq_record in enumerate(sequences):
            filename = f"sequence_{i+1}.fasta"
            filepath = os.path.join(output_path, filename)
            SeqIO.write(seq_record, filepath, "fasta")
            
        return output_path
        
    except Exception as e:
        print(f"Error processing FASTA file: {e}")
        return None

def create_alignment_and_contigs(input_path, output_folder):
    """Create a consensus sequence from multiple FASTA files."""
    try:
        # Check if input_path is a directory or a file
        if os.path.isdir(input_path):
            # Get absolute paths to input files in the directory
            input_files = [os.path.join(input_path, file) for file in os.listdir(input_path) if file.endswith(".fasta")]
        else:
            # Input is a single file
            input_files = [input_path]

        if not input_files:
            print(f"No FASTA files found in {input_path}")
            return None

        # Read sequences from input files
        sequences = []
        for file in input_files:
            try:
                # Try to read as a single sequence file
                seq_record = SeqIO.read(file, "fasta")
                sequences.append(seq_record)
            except:
                # If that fails, try to read as a multi-sequence file
                try:
                    file_sequences = list(SeqIO.parse(file, "fasta"))
                    sequences.extend(file_sequences)
                except Exception as e:
                    print(f"Error reading {file}: {e}")

        if not sequences:
            print(f"No valid sequences found in {input_path}")
            return None

        # Find the maximum length among all sequences
        max_length = max(len(seq) for seq in sequences)

        # Pad shorter sequences with gaps ('-') to make them of equal length
        aligned_sequences = [str(seq.seq).ljust(max_length, '-') for seq in sequences]

        # Calculate the consensus sequence based on the most frequent nucleotide at each position
        # Replace gaps with 'N' to make it valid for primer design
        consensus_seq = ''.join(
            Counter(col).most_common(1)[0][0] if Counter(col).most_common(1)[0][0] != '-' else 'N' 
            for col in zip(*aligned_sequences)
        )

        # Create a SeqRecord for the consensus sequence
        consensus_record = SeqRecord(Seq(consensus_seq), id="Consensus_Sequence", description="")

        # Save the consensus sequence to a FASTA file
        output_file = os.path.join(output_folder, "Consensus_Sequence.fasta")
        SeqIO.write(consensus_record, output_file, "fasta")

        print(f"Consensus sequence saved to {output_file}")
        return output_file

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def check_primer_properties(forward_primer, reverse_primer, max_poly_x=3, gc_percent_range=(40, 70), max_tm_difference=2):
    """Check if primers meet specified criteria."""
    poly_x = max(forward_primer.count('X'), reverse_primer.count('X'))
    if poly_x > max_poly_x:
        return False
    
    gc_percent_forward = (forward_primer.count('G') + forward_primer.count('C')) / len(forward_primer) * 100
    gc_percent_reverse = (reverse_primer.count('G') + reverse_primer.count('C')) / len(reverse_primer) * 100
    if not (gc_percent_range[0] <= gc_percent_forward <= gc_percent_range[1] and
            gc_percent_range[0] <= gc_percent_reverse <= gc_percent_range[1]):
        return False
    
    tm_difference = abs(MeltingTemp.Tm_Wallace(forward_primer) - MeltingTemp.Tm_Wallace(reverse_primer))
    if tm_difference > max_tm_difference:
        return False
    
    return True

def design_primers(fasta_path, output_path, num_primers=3, product_size_range=(250, 1000), tm_range=(58, 64)):
    """Design primers using primer3."""
    try:
        with open(fasta_path, 'r') as fasta_file:
            record = SeqIO.read(fasta_file, 'fasta')

        primer_pairs = []
        for i in range(num_primers):
            # Define a target region
            product_size = random.randint(*product_size_range)
            target_start = random.randint(0, len(record.seq) - product_size)
            target_end = target_start + product_size

            # Extract the target sequence and replace any invalid characters
            target_sequence = str(record.seq[target_start:target_end]).replace('-', 'N')

            # Design primers using primer3
            primers = primer3.bindings.design_primers(
                {
                    'SEQUENCE_ID': 'target',
                    'SEQUENCE_TEMPLATE': target_sequence,
                    'SEQUENCE_INCLUDED_REGION': [0, len(target_sequence)],
                },
                {
                    'PRIMER_OPT_SIZE': 20,
                    'PRIMER_PICK_INTERNAL_OLIGO': 1,
                    'PRIMER_INTERNAL_MAX_SELF_END': 8,
                    'PRIMER_MIN_SIZE': 18,
                    'PRIMER_MAX_SIZE': 24,
                    'PRIMER_MAX_POLY_X': 3,
                    'PRIMER_INTERNAL_OPT_SIZE': 20,
                    'PRIMER_INTERNAL_MIN_SIZE': 18,
                    'PRIMER_INTERNAL_MAX_SIZE': 24,
                    'PRIMER_INTERNAL_MAX_POLY_X': 3,
                    'PRIMER_INTERNAL_MAX_SELF_END': 8,
                    'PRIMER_INTERNAL_MAX_SELF_END_TH': 47,
                    'PRIMER_INTERNAL_MAX_HAIRPIN_TH': 47,
                    'PRIMER_INTERNAL_MIN_TM': tm_range[0],
                    'PRIMER_INTERNAL_OPT_TM': (tm_range[0] + tm_range[1]) / 2,
                    'PRIMER_INTERNAL_MAX_TM': tm_range[1],
                    'PRIMER_INTERNAL_MIN_GC': 40,
                    'PRIMER_INTERNAL_OPT_GC_PERCENT': (40 + 70) / 2,
                    'PRIMER_INTERNAL_MAX_GC': 70,
                    'PRIMER_PAIR_MAX_DIFF_TM': 2,
                }
            )

            # Extract forward and reverse primers
            if 'PRIMER_LEFT_0_SEQUENCE' in primers and 'PRIMER_RIGHT_0_SEQUENCE' in primers:
                forward_primer = primers['PRIMER_LEFT_0_SEQUENCE']
                reverse_primer = primers['PRIMER_RIGHT_0_SEQUENCE']

                # Check if the primers meet the specified criteria
                if check_primer_properties(forward_primer, reverse_primer):
                    primer_pairs.append((forward_primer, reverse_primer,
                                         MeltingTemp.Tm_Wallace(forward_primer), MeltingTemp.Tm_Wallace(reverse_primer),
                                         len(forward_primer), product_size))

        # Save primer pairs to a file
        output_file_path = os.path.join(output_path, 'primer_pairs.txt')
        with open(output_file_path, 'w') as output_file:
            output_file.write("Forward Primer\tReverse Primer\tTm Forward\tTm Reverse\tPrimer Length\tProduct Size\n")
            for forward, reverse, tm_forward, tm_reverse, primer_length, product_size in primer_pairs:
                output_file.write(f"{forward}\t{reverse}\t{tm_forward}\t{tm_reverse}\t{primer_length}\t{product_size}\n")

        print(f"Primer pairs saved to: {output_file_path}")
        return output_file_path
    
    except Exception as e:
        print(f"Error designing primers: {e}")
        return None

def design_primers_with_tuning(fasta_path, output_path, num_primers=3, product_size_range=(250, 1000), tm_range=(58, 64)):
    """Design primers with parameter tuning and machine learning."""
    try:
        with open(fasta_path, 'r') as fasta_file:
            record = SeqIO.read(fasta_file, 'fasta')

        # Extract features and labels for machine learning model training
        X = []
        y = []

        primer_pairs = []
        for i in range(num_primers):
            # Define a target region
            product_size = random.randint(*product_size_range)
            target_start = random.randint(0, len(record.seq) - product_size)
            target_end = target_start + product_size

            # Extract the target sequence and replace any invalid characters
            target_sequence = str(record.seq[target_start:target_end]).replace('-', 'N')

            # Design primers using primer3
            primers = primer3.bindings.design_primers(
                {
                    'SEQUENCE_ID': 'target',
                    'SEQUENCE_TEMPLATE': target_sequence,
                    'SEQUENCE_INCLUDED_REGION': [0, len(target_sequence)],
                },
                {
                    'PRIMER_OPT_SIZE': 20,
                    'PRIMER_PICK_INTERNAL_OLIGO': 1,
                    'PRIMER_INTERNAL_MAX_SELF_END': 8,
                    'PRIMER_MIN_SIZE': 18,
                    'PRIMER_MAX_SIZE': 24,
                    'PRIMER_MAX_POLY_X': 3,
                    'PRIMER_INTERNAL_OPT_SIZE': 20,
                    'PRIMER_INTERNAL_MIN_SIZE': 18,
                    'PRIMER_INTERNAL_MAX_SIZE': 24,
                    'PRIMER_INTERNAL_MAX_POLY_X': 3,
                    'PRIMER_INTERNAL_MAX_SELF_END': 8,
                    'PRIMER_INTERNAL_MAX_SELF_END_TH': 47,
                    'PRIMER_INTERNAL_MAX_HAIRPIN_TH': 47,
                    'PRIMER_INTERNAL_MIN_TM': tm_range[0],
                    'PRIMER_INTERNAL_OPT_TM': (tm_range[0] + tm_range[1]) / 2,
                    'PRIMER_INTERNAL_MAX_TM': tm_range[1],
                    'PRIMER_INTERNAL_MIN_GC': 40,
                    'PRIMER_INTERNAL_OPT_GC_PERCENT': (40 + 70) / 2,
                    'PRIMER_INTERNAL_MAX_GC': 70,
                    'PRIMER_PAIR_MAX_DIFF_TM': 2,
                }
            )

            # Extract forward and reverse primers
            if 'PRIMER_LEFT_0_SEQUENCE' in primers and 'PRIMER_RIGHT_0_SEQUENCE' in primers:
                forward_primer = primers['PRIMER_LEFT_0_SEQUENCE']
                reverse_primer = primers['PRIMER_RIGHT_0_SEQUENCE']

                # Check if the primers meet the specified criteria
                if check_primer_properties(forward_primer, reverse_primer):
                    primer_pairs.append((forward_primer, reverse_primer,
                                         MeltingTemp.Tm_Wallace(forward_primer), MeltingTemp.Tm_Wallace(reverse_primer),
                                         len(forward_primer), product_size))

                    # Define a success label based on your criteria
                    primer_success = True  # You need to define your own criteria for success

                    # Append features and labels for machine learning model training
                    X.append([len(forward_primer), product_size])
                    y.append(primer_success)

        # Convert primer pairs to DataFrame for RandomizedSearchCV
        df = pd.DataFrame(primer_pairs, columns=['Forward Primer', 'Reverse Primer', 'Tm Forward', 'Tm Reverse', 'Primer Length', 'Product Size'])

        # Add 'Primer Success' column to the DataFrame
        df['Primer Success'] = y

        # Extract features and labels for machine learning model training
        X = df[['Primer Length', 'Product Size']]
        y = df['Primer Success']

        # Define the parameter grid for RandomizedSearchCV
        param_dist = {
            'n_estimators': [50, 100, 150, 200],
            'max_depth': [None, 10, 20, 30],
            'min_samples_split': [2, 5, 10],
            'min_samples_leaf': [1, 2, 4]
        }

        # Initialize the RandomForestClassifier
        rf = RandomForestClassifier()

        # Initialize RandomizedSearchCV
        random_search = RandomizedSearchCV(rf, param_distributions=param_dist, n_iter=5, cv=3, verbose=1, n_jobs=-1, random_state=42)

        # Fit the RandomizedSearchCV to the data
        random_search.fit(X, y)

        # Get the best parameters from the search
        best_params = random_search.best_params_
        print("Best Parameters:", best_params)

        # Train a model with the best parameters
        best_rf_model = RandomForestClassifier(**best_params)
        best_rf_model.fit(X, y)

        print("Model training and tuning completed.")
        return True
    
    except Exception as e:
        print(f"Error in primer tuning: {e}")
        return False

def check_primer_dimers(forward_primer, reverse_primer):
    """Calculate dimer information using primer3-py."""
    dimer_info = calc_heterodimer(forward_primer, reverse_primer)
    return dimer_info.dg, dimer_info.tm

def check_primer_quality(forward_primer, reverse_primer):
    """Check primer quality based on various criteria."""
    # Calculate primer length
    primer_length_forward = len(forward_primer)
    primer_length_reverse = len(reverse_primer)

    # Calculate GC content as a fraction
    gc_content_forward = gc_fraction(forward_primer)
    gc_content_reverse = gc_fraction(reverse_primer)

    # Check for optimal primer length (adjust the thresholds as needed)
    optimal_length = 18 <= primer_length_forward <= 25 and 18 <= primer_length_reverse <= 25

    # Check for similar melting temperatures (adjust the threshold as needed)
    similar_tm = abs(MeltingTemp.Tm_NN(Seq(forward_primer)) - MeltingTemp.Tm_NN(Seq(reverse_primer))) <= 2

    # Check for optimal GC content (adjust the thresholds as needed)
    optimal_gc = 0.4 <= gc_content_forward <= 0.6 and 0.4 <= gc_content_reverse <= 0.6

    return optimal_length, similar_tm, optimal_gc

def visualize_primer_dimer(forward_primer, reverse_primer, output_path, index):
    """Visualize melting curves for primers."""
    forward_seq = Seq(forward_primer)
    reverse_seq = Seq(reverse_primer)

    tm_forward = MeltingTemp.Tm_NN(forward_seq)
    tm_reverse = MeltingTemp.Tm_NN(reverse_seq)

    temperatures = np.arange(45, 100)
    melting_curve_forward = [MeltingTemp.Tm_NN(forward_seq)] * len(temperatures)
    melting_curve_reverse = [MeltingTemp.Tm_NN(reverse_seq)] * len(temperatures)

    plt.figure(figsize=(10, 6))
    plt.plot(temperatures, melting_curve_forward, label=f"Forward Primer (Tm={tm_forward:.2f})")
    plt.plot(temperatures, melting_curve_reverse, label=f"Reverse Primer (Tm={tm_reverse:.2f})")

    plt.xlabel('Temperature (°C)')
    plt.ylabel('Melting Temperature (°C)')
    plt.title(f'Melting Curves of Primers (Pair {index+1})')
    plt.legend()
    plt.grid(True)
    
    # Save the plot
    plot_path = os.path.join(output_path, f"primer_melting_curve_{index+1}.png")
    plt.savefig(plot_path)
    plt.close()
    
    print(f"Melting curve plot saved to: {plot_path}")

def analyze_primers(primer_file_path, output_path):
    """Analyze primer pairs for dimers and quality."""
    try:
        with open(primer_file_path, 'r') as file:
            lines = file.readlines()

        if len(lines) <= 1:
            print("No primer pairs found in the file.")
            return None

        # Create output directory for plots
        plot_dir = os.path.join(output_path, "plots")
        os.makedirs(plot_dir, exist_ok=True)
        
        # Open the output file for writing results
        output_file_path = os.path.join(output_path, "primer_analysis_results.txt")
        with open(output_file_path, 'w') as output_file:
            # Write extended header to the output file
            output_file.write("Forward Primer\tReverse Primer\tDimer Delta G\tDimer Tm\tOptimal Length\tSimilar Tm\tOptimal GC\n")

            # Process each line in the input file
            for i, line in enumerate(lines[1:]):  # Skip the header line
                fields = line.strip().split('\t')
                if len(fields) < 2:
                    continue
                    
                forward_primer = fields[0]
                reverse_primer = fields[1]

                # Check for primer dimers and get dimer information
                dimer_delta_g, dimer_tm = check_primer_dimers(forward_primer, reverse_primer)

                # Check primer quality
                optimal_length, similar_tm, optimal_gc = check_primer_quality(forward_primer, reverse_primer)

                # Write results to the output file
                output_file.write(f"{forward_primer}\t{reverse_primer}\t{dimer_delta_g:.2f}\t{dimer_tm:.2f}\t{optimal_length}\t{similar_tm}\t{optimal_gc}\n")

                # Visualize primer dimers
                visualize_primer_dimer(forward_primer, reverse_primer, plot_dir, i)

        print(f"Primer analysis results saved to: {output_file_path}")
        return output_file_path
    
    except Exception as e:
        print(f"Error analyzing primers: {e}")
        return None

def run_primer_blast(forward_primer, reverse_primer, output_file):
    """Perform Primer-BLAST for a given primer pair."""
    try:
        # Combine forward and reverse primers into a single sequence
        sequence = Seq(f'{forward_primer}{reverse_primer}')
        
        # Create a SeqRecord object for the sequence
        seq_record = SeqRecord(sequence, id=output_file, description="")
        
        # Perform Primer-BLAST
        result_handle = NCBIWWW.qblast(
            program="blastn",
            database="nr",  # Use the nr nucleotide database
            sequence=seq_record.format("fasta"),
            word_size=7,
            expect=100.0,
            hitlist_size=5,
            descriptions=5,
            alignments=5,
            entrez_query="txid3193[ORGN] OR txid10239[ORGN]",  # Update the entrez_query
        )
        
        # Save the result to a file
        print(f"Saving BLAST result to {output_file}")
        with open(output_file, "w") as out_handle:
            result_content = result_handle.read()
            out_handle.write(result_content)
            print(f"Result size: {len(result_content)} bytes")
        
        # Close the result handle
        result_handle.close()
        return True
        
    except Exception as e:
        print(f"Error processing {output_file}: {e}")
        return False

def blast_all_primers(primer_file_path, output_directory):
    """Run Primer-BLAST for all primer pairs."""
    try:
        # Ensure the output directory exists
        os.makedirs(output_directory, exist_ok=True)

        # Read primer pairs from the input file into a DataFrame
        primers_df = pd.read_csv(primer_file_path, delimiter='\t')

        # Iterate over rows in the DataFrame and perform Primer-BLAST
        for index, row in primers_df.iterrows():
            forward_primer = row['Forward Primer']
            reverse_primer = row['Reverse Primer']
            
            # Run Primer-BLAST for the current primer pair
            output_file_name = os.path.join(output_directory, f'primer_blast_result_{index}.xml')
            success = run_primer_blast(forward_primer, reverse_primer, output_file_name)
            
            if success:
                # Add a delay to prevent throttling by NCBI servers
                time.sleep(5)

        # Display a message indicating the completion of the Primer-BLAST for all primer pairs
        print('Primer-BLAST completed for all primer pairs.')
        return True
        
    except Exception as e:
        print(f"Error in BLAST analysis: {e}")
        return False

def parse_blast_xml(xml_file_path):
    """Parse a single BLAST XML file and extract relevant information."""
    try:
        with open(xml_file_path) as result_handle:
            blast_records = NCBIXML.parse(result_handle)
            data = []
            for blast_record in blast_records:
                for alignment in blast_record.alignments:
                    for hsp in alignment.hsps:
                        data.append({
                            'Primer Pair File': os.path.basename(xml_file_path),
                            'Hit ID': alignment.hit_id,
                            'Hit Description': alignment.hit_def,
                            'Alignment Length': hsp.align_length,
                            'E-value': hsp.expect,
                            'Score': hsp.score,
                            'Identity': hsp.identities,
                            'Gaps': hsp.gaps,
                        })
            return pd.DataFrame(data)
    except Exception as e:
        print(f"Error parsing {xml_file_path}: {e}")
        return pd.DataFrame()

def parse_all_blast_results(output_directory):
    """Parse all BLAST XML files and save results to CSV."""
    try:
        # Parse all XML files in the output directory
        result_files = [f for f in os.listdir(output_directory) if f.endswith('.xml')]
        all_results = []

        for xml_file in result_files:
            xml_file_path = os.path.join(output_directory, xml_file)
            print(f"Parsing {xml_file_path}")
            df = parse_blast_xml(xml_file_path)
            if not df.empty:
                all_results.append(df)

        # Combine all results into a single DataFrame
        if all_results:
            final_results = pd.concat(all_results, ignore_index=True)
        else:
            final_results = pd.DataFrame(columns=['Primer Pair File', 'Hit ID', 'Hit Description', 
                                                  'Alignment Length', 'E-value', 'Score', 'Identity', 'Gaps'])

        # Save the results to a CSV file
        output_csv_path = os.path.join(output_directory, "all_primer_blast_results.csv")
        final_results.to_csv(output_csv_path, index=False)

        print(f"All results saved to {output_csv_path}")
        return output_csv_path
        
    except Exception as e:
        print(f"Error parsing BLAST results: {e}")
        return None

def main():
    """Main function to run the complete pipeline."""
    args = parse_arguments()
    
    # Set NCBI email
    Entrez.email = args.email
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output, exist_ok=True)
    
    try:
        # Step 1: Get input sequences
        print("Step 1: Processing input sequences...")
        
        if args.virus:
            # Download sequences from NCBI
            sequences_path = download_all_sequences(args.virus, args.output, args.max_sequences)
            if not sequences_path:
                print("Failed to download sequences. Exiting.")
                return
        else:
            # Use existing FASTA file
            sequences_path = process_fasta_file(args.fasta, os.path.join(args.output, "input_sequences"))
            if not sequences_path:
                print("Failed to process FASTA file. Exiting.")
                return
        
        # Step 2: Create consensus sequence
        print("Step 2: Creating consensus sequence...")
        consensus_file = create_alignment_and_contigs(sequences_path, args.output)
        
        if not consensus_file:
            print("Failed to create consensus sequence. Exiting.")
            return
        
        # Step 3: Design primers
        print("Step 3: Designing primers...")
        primer_file = design_primers(
            consensus_file, 
            args.output, 
            num_primers=args.num_primers,
            product_size_range=(args.product_size_min, args.product_size_max),
            tm_range=(args.tm_min, args.tm_max)
        )
        
        if not primer_file:
            print("Failed to design primers. Exiting.")
            return
        
        # Optional: Design primers with tuning
        if not args.skip_tuning:
            print("Step 3a: Designing primers with tuning...")
            design_primers_with_tuning(
                consensus_file,
                args.output,
                num_primers=args.num_primers,
                product_size_range=(args.product_size_min, args.product_size_max),
                tm_range=(args.tm_min, args.tm_max)
            )
        
        # Step 4: Analyze primers
        print("Step 4: Analyzing primers...")
        analyze_primers(primer_file, args.output)
        
        # Step 5: Run Primer-BLAST (unless skipped)
        if not args.skip_blast:
            print("Step 5: Running Primer-BLAST...")
            blast_output_dir = os.path.join(args.output, "blast_results")
            blast_all_primers(primer_file, blast_output_dir)
            
            # Step 6: Parse BLAST results
            print("Step 6: Parsing BLAST results...")
            parse_all_blast_results(blast_output_dir)
        else:
            print("Skipping BLAST validation step...")
        
        print("Pipeline completed successfully!")
        print(f"All results saved to: {args.output}")
        
    except KeyboardInterrupt:
        print("The process was interrupted by the user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
