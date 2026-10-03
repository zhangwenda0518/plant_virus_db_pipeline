"""
PAmiRDB Database Models (SQLite).

Schema matches the PAmiRDB paper's data model:
  - miRNAs (plant miRNA sequences with metadata)
  - Viruses (genome sequences with taxonomic info)
  - VirusHost (host range relationships)
  - Predictions (miRNA-target interaction predictions)
"""

from pathlib import Path
import json
import sys

try:
    from sqlalchemy import (
        create_engine, Column, Integer, String, Float, Boolean,
        Text, ForeignKey, Index
    )
    from sqlalchemy.orm import declarative_base, Session, relationship
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    print("Warning: SQLAlchemy not available. Using JSON file storage.")
    print("Run: pip install sqlalchemy")

Base = declarative_base() if SQLALCHEMY_AVAILABLE else None


class MiRNA(Base):
    """Plant miRNA entry."""
    __tablename__ = 'mirnas'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    mirna_id = Column(String(50), unique=True, nullable=False, index=True)
    sequence = Column(String(100), nullable=False)
    length = Column(Integer)
    species_code = Column(String(10))
    species_name = Column(String(100))
    
    predictions = relationship("Prediction", back_populates="mirna")


class Virus(Base):
    """Virus genome entry."""
    __tablename__ = 'viruses'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    virus_id = Column(String(50), unique=True, nullable=False, index=True)
    accession = Column(String(50))
    name = Column(String(200))
    family = Column(String(50))
    genome_length = Column(Integer)
    sequence = Column(Text)
    
    predictions = relationship("Prediction", back_populates="virus")


class VirusHost(Base):
    """Virus-host relationship."""
    __tablename__ = 'virus_hosts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    virus_id = Column(String(50), ForeignKey('viruses.virus_id'), nullable=False)
    virus_name = Column(String(200))
    host_species = Column(String(100))
    host_common_name = Column(String(100))


class Prediction(Base):
    """miRNA-target prediction result."""
    __tablename__ = 'predictions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    mirna_id = Column(String(50), ForeignKey('mirnas.mirna_id'), nullable=False, index=True)
    virus_id = Column(String(50), ForeignKey('viruses.virus_id'), nullable=False, index=True)
    target_start = Column(Integer)
    target_end = Column(Integer)
    score = Column(Float)
    energy = Column(Float)
    num_mismatches = Column(Integer)
    num_gaps = Column(Integer)
    seed_perfect = Column(Boolean)
    query_cover = Column(Float)
    identity = Column(Float)
    alignment = Column(Text)
    
    mirna = relationship("MiRNA", back_populates="predictions")
    virus = relationship("Virus", back_populates="predictions")
    
    __table_args__ = (
        Index('idx_mirna_virus', 'mirna_id', 'virus_id'),
    )


class Database:
    """PAmiRDB database manager."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "pamirdb.sqlite")
        
        if not SQLALCHEMY_AVAILABLE:
            self.engine = None
            self.db_path = db_path
            self._use_json_fallback()
            return
        
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self.db_path = db_path
    
    def _use_json_fallback(self):
        """Use JSON files as fallback storage."""
        self._json_data = {
            'mirnas': {},
            'viruses': {},
            'virus_hosts': [],
            'predictions': [],
        }
        data_dir = Path(self.db_path).parent
        
        mirna_file = data_dir / "mirna" / "plant_mirnas.json"
        if mirna_file.exists():
            with open(mirna_file) as f:
                self._json_data['mirnas'] = json.load(f)
        
        virus_file = data_dir / "virus_genomes" / "viruses.json"
        if virus_file.exists():
            with open(virus_file) as f:
                self._json_data['viruses'] = json.load(f)
        
        pred_file = data_dir / "predictions.json"
        if pred_file.exists():
            with open(pred_file) as f:
                self._json_data['predictions'] = json.load(f)
    
    def create_tables(self):
        """Create all database tables."""
        if self.engine:
            Base.metadata.create_all(self.engine)
            print("[OK]Database tables created.")
    
    def load_data_files(self):
        """Load data from JSON files into the database."""
        data_dir = Path(self.db_path).parent
        
        # Load miRNAs
        mirna_file = data_dir / "mirna" / "plant_mirnas.json"
        if mirna_file.exists():
            with open(mirna_file) as f:
                mirnas = json.load(f)
            
            if self.engine:
                with Session(self.engine) as session:
                    for mirna_id, info in mirnas.items():
                        session.add(MiRNA(
                            mirna_id=mirna_id,
                            sequence=info['sequence'],
                            length=info.get('length', len(info['sequence'])),
                            species_code=info.get('species_code', ''),
                            species_name=info.get('species_name', ''),
                        ))
                    session.commit()
                print(f"[OK]Loaded {len(mirnas)} miRNAs into database.")
        
        # Load viruses
        virus_file = data_dir / "virus_genomes" / "viruses.json"
        fasta_file = data_dir / "virus_genomes" / "viruses.fasta"
        virus_seqs = {}
        if fasta_file.exists():
            current_id = None
            current_seq = []
            with open(fasta_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('>'):
                        if current_id:
                            virus_seqs[current_id] = ''.join(current_seq)
                        current_id = line[1:].split('|')[0]
                        current_seq = []
                    else:
                        current_seq.append(line)
                if current_id:
                    virus_seqs[current_id] = ''.join(current_seq)
        
        if virus_file.exists():
            with open(virus_file) as f:
                viruses = json.load(f)
            
            if self.engine:
                with Session(self.engine) as session:
                    for vid, info in viruses.items():
                        session.add(Virus(
                            virus_id=vid,
                            accession=info.get('accession', ''),
                            name=info.get('name', ''),
                            family=info.get('family', ''),
                            genome_length=info.get('genome_length', 0),
                            sequence=virus_seqs.get(vid, ''),
                        ))
                    session.commit()
                print(f"[OK]Loaded {len(viruses)} viruses into database.")
        
        # Load predictions if available
        pred_file = data_dir / "predictions.json"
        if pred_file.exists():
            with open(pred_file) as f:
                predictions = json.load(f)
            
            if self.engine:
                with Session(self.engine) as session:
                    for p in predictions:
                        session.add(Prediction(
                            mirna_id=p['mirna_id'],
                            virus_id=p['target_virus_id'],
                            target_start=p['target_start'],
                            target_end=p['target_end'],
                            score=p['score'],
                            energy=p['energy'],
                            num_mismatches=p['num_mismatches'],
                            num_gaps=p['num_gaps'],
                            seed_perfect=p['seed_perfect'],
                            query_cover=p['query_cover'],
                            identity=p['identity'],
                            alignment=p['alignment'],
                        ))
                    session.commit()
                print(f"[OK]Loaded {len(predictions)} predictions into database.")
    
    def query(self, **filters):
        """
        Query predictions with filters matching PAmiRDB interface.
        
        Filters supported:
          - mirna_id: specific miRNA(s)
          - virus_id: specific virus
          - virus_family: geminiviridae or potyviridae
          - plant_species: species code (ath, gma, osa, etc.)
          - seed_region: list of positions that must match
          - max_energy: maximum interaction energy
          - min_identity: minimum % identity
          - min_query_cover: minimum % query coverage
        """
        if not self.engine:
            # JSON fallback query
            return self._json_query(**filters)
        
        from sqlalchemy import and_
        
        with Session(self.engine) as session:
            query = session.query(Prediction).join(MiRNA).join(Virus)
            conditions = []
            
            if 'mirna_id' in filters:
                conditions.append(Prediction.mirna_id == filters['mirna_id'])
            
            if 'virus_id' in filters:
                conditions.append(Prediction.virus_id == filters['virus_id'])
            
            if 'virus_family' in filters:
                conditions.append(Virus.family == filters['virus_family'])
            
            if 'plant_species' in filters:
                conditions.append(MiRNA.species_code == filters['plant_species'])
            
            if 'max_energy' in filters:
                conditions.append(Prediction.energy <= filters['max_energy'])
            
            if 'min_identity' in filters:
                conditions.append(Prediction.identity >= filters['min_identity'])
            
            if 'min_query_cover' in filters:
                conditions.append(Prediction.query_cover >= filters['min_query_cover'])
            
            if conditions:
                query = query.filter(and_(*conditions))
            
            results = query.all()
            
            return [
                {
                    "mirna_id": r.mirna_id,
                    "mirna_seq": r.mirna.sequence,
                    "species_name": r.mirna.species_name,
                    "virus_id": r.virus_id,
                    "virus_name": r.virus.name,
                    "virus_family": r.virus.family,
                    "target_start": r.target_start,
                    "target_end": r.target_end,
                    "score": r.score,
                    "energy": r.energy,
                    "num_mismatches": r.num_mismatches,
                    "num_gaps": r.num_gaps,
                    "seed_perfect": r.seed_perfect,
                    "query_cover": r.query_cover,
                    "identity": r.identity,
                    "alignment": r.alignment,
                }
                for r in results
            ]
    
    def _json_query(self, **filters) -> list[dict]:
        """Fallback query using in-memory JSON data."""
        results = []
        preds = self._json_data.get('predictions', [])
        mirnas = self._json_data.get('mirnas', {})
        viruses = self._json_data.get('viruses', {})
        
        for p in preds:
            # Apply filters
            if 'mirna_id' in filters and p['mirna_id'] != filters['mirna_id']:
                continue
            if 'virus_id' in filters and p.get('target_virus_id') != filters['virus_id']:
                continue
            if 'virus_family' in filters and p.get('target_virus_family') != filters['virus_family']:
                continue
            if 'plant_species' in filters and p.get('mirna_species') != filters['plant_species']:
                continue
            if 'max_energy' in filters and p.get('energy', 0) > filters['max_energy']:
                continue
            if 'min_identity' in filters and p.get('identity', 0) < filters['min_identity']:
                continue
            
            # Enrich with species/virus names
            mirna_info = mirnas.get(p['mirna_id'], {})
            virus_info = viruses.get(p.get('target_virus_id', ''), {})
            
            results.append({
                **p,
                'species_name': mirna_info.get('species_name', ''),
                'virus_name': virus_info.get('name', ''),
                'virus_family': virus_info.get('family', ''),
            })
        
        return results
    
    def get_mirnas(self) -> list[dict]:
        """Get all miRNA entries."""
        if not self.engine:
            return [{'mirna_id': k, **v} for k, v in self._json_data['mirnas'].items()]
        
        with Session(self.engine) as session:
            return [
                {
                    'mirna_id': m.mirna_id,
                    'sequence': m.sequence,
                    'species_code': m.species_code,
                    'species_name': m.species_name,
                }
                for m in session.query(MiRNA).all()
            ]
    
    def get_viruses(self) -> list[dict]:
        """Get all virus entries."""
        if not self.engine:
            return [{'virus_id': k, **v} for k, v in self._json_data['viruses'].items()]
        
        with Session(self.engine) as session:
            return [
                {
                    'virus_id': v.virus_id,
                    'accession': v.accession,
                    'name': v.name,
                    'family': v.family,
                    'genome_length': v.genome_length,
                }
                for v in session.query(Virus).all()
            ]
    
    def get_virus_hosts(self, virus_id: str = None) -> list[dict]:
        """Get virus-host relationships."""
        if not self.engine:
            hosts = self._json_data.get('virus_hosts', [])
            if virus_id:
                hosts = [h for h in hosts if h.get('virus_id') == virus_id]
            return hosts
        
        with Session(self.engine) as session:
            query = session.query(VirusHost)
            if virus_id:
                query = query.filter(VirusHost.virus_id == virus_id)
            return [
                {
                    'virus_id': h.virus_id,
                    'virus_name': h.virus_name,
                    'host_species': h.host_species,
                    'host_common_name': h.host_common_name,
                }
                for h in query.all()
            ]


if __name__ == '__main__':
    db = Database()
    db.create_tables()
    db.load_data_files()
