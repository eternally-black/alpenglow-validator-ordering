//! Raw-data writers. Everything a run observes is appended to files under its run directory as it happens, so a
//! crash loses nothing that was already sent. Large JSON (gossip, blocks) is zstd-compressed.

use anyhow::{Context, Result};
use serde::Serialize;
use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

pub struct RunDir {
    pub path: PathBuf,
}

impl RunDir {
    /// Creates a fresh run directory; an existing one is refused (two runs never share a directory).
    pub fn create(path: PathBuf) -> Result<Self> {
        if path.exists() {
            anyhow::bail!("run directory {} already exists", path.display());
        }
        std::fs::create_dir_all(path.join("blocks")).with_context(|| format!("creating {}", path.display()))?;
        Ok(Self { path })
    }

    pub fn jsonl(&self, name: &str) -> Result<Jsonl> {
        Jsonl::open(&self.path.join(name))
    }

    pub fn write_json(&self, name: &str, value: &impl Serialize) -> Result<()> {
        let f = File::create(self.path.join(name))?;
        serde_json::to_writer_pretty(BufWriter::new(f), value)?;
        Ok(())
    }

    pub fn write_zst(&self, name: &str, value: &impl Serialize) -> Result<()> {
        write_zst(&self.path.join(name), value)
    }
}

pub fn write_zst(path: &Path, value: &impl Serialize) -> Result<()> {
    let f = File::create(path).with_context(|| format!("creating {}", path.display()))?;
    let mut enc = zstd::Encoder::new(f, 12)?;
    serde_json::to_writer(&mut enc, value)?;
    enc.finish()?.sync_all()?;
    Ok(())
}

/// Append-only JSON-lines file, flushed after every record.
pub struct Jsonl {
    w: Mutex<BufWriter<File>>,
}

impl Jsonl {
    pub fn open(path: &Path) -> Result<Self> {
        let f = OpenOptions::new().create(true).append(true).open(path).with_context(|| format!("opening {}", path.display()))?;
        Ok(Self { w: Mutex::new(BufWriter::new(f)) })
    }

    pub fn append(&self, value: &impl Serialize) -> Result<()> {
        let mut w = self.w.lock().expect("jsonl mutex");
        serde_json::to_writer(&mut *w, value)?;
        w.write_all(b"\n")?;
        w.flush()?;
        Ok(())
    }

    /// Append and fsync: for journal transitions that must survive power loss (attempt claims, terminal states).
    pub fn append_durable(&self, value: &impl Serialize) -> Result<()> {
        let mut w = self.w.lock().expect("jsonl mutex");
        serde_json::to_writer(&mut *w, value)?;
        w.write_all(b"\n")?;
        w.flush()?;
        w.get_ref().sync_data()?;
        Ok(())
    }
}

pub fn utc_now_rfc3339() -> String {
    time::OffsetDateTime::now_utc().format(&time::format_description::well_known::Rfc3339).unwrap_or_default()
}

/// `20261023T171500Z-<tag>-<4 hex>`: sortable, filesystem-safe, collision-resistant run id.
pub fn new_run_id(tag: &str) -> String {
    let now = time::OffsetDateTime::now_utc();
    let fmt = time::macros::format_description!("[year][month][day]T[hour][minute][second]Z");
    format!("{}-{tag}-{:04x}", now.format(&fmt).unwrap_or_default(), rand::random::<u16>())
}
