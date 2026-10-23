//! Keys are read from paths supplied by env or flags (mounted volumes in Docker) and never written into the repo.

use anyhow::{Context, Result, bail};
use solana_keypair::Keypair;
use std::path::{Path, PathBuf};

/// Reads a Solana CLI keypair file (a JSON array of 64 bytes).
pub fn read_keypair(path: &Path) -> Result<Keypair> {
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("reading keypair {}", path.display()))?;
    let bytes: Vec<u8> = serde_json::from_str(&text)
        .with_context(|| format!("{} is not a keypair JSON array", path.display()))?;
    if bytes.len() != 64 {
        bail!(
            "{}: expected 64 bytes, found {}",
            path.display(),
            bytes.len()
        );
    }
    Keypair::try_from(bytes.as_slice())
        .map_err(|e| anyhow::anyhow!("{}: invalid keypair: {e}", path.display()))
}

pub fn write_keypair(path: &Path, kp: &Keypair) -> Result<()> {
    if path.exists() {
        bail!("refusing to overwrite existing keypair {}", path.display());
    }
    let json = serde_json::to_string(&kp.to_bytes().to_vec())?;
    std::fs::write(path, json).with_context(|| format!("writing {}", path.display()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

/// The payer pool: `payer-000.json` … in one directory, created by `itb init-payers`.
pub fn payer_paths(dir: &Path) -> Result<Vec<PathBuf>> {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(dir)
        .with_context(|| format!("reading payer dir {}", dir.display()))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            p.file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.starts_with("payer-") && n.ends_with(".json"))
        })
        .collect();
    paths.sort();
    Ok(paths)
}

pub fn load_payers(dir: &Path) -> Result<Vec<Keypair>> {
    payer_paths(dir)?.iter().map(|p| read_keypair(p)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use solana_signer::Signer;

    #[test]
    fn keypair_roundtrip_and_no_overwrite() {
        let dir = std::env::temp_dir().join(format!("itb-keys-test-{}", rand::random::<u64>()));
        std::fs::create_dir_all(&dir).unwrap();
        let kp = Keypair::new();
        let path = dir.join("payer-000.json");
        write_keypair(&path, &kp).unwrap();
        assert_eq!(read_keypair(&path).unwrap().pubkey(), kp.pubkey());
        assert!(write_keypair(&path, &Keypair::new()).is_err());
        assert_eq!(load_payers(&dir).unwrap().len(), 1);
    }
}
