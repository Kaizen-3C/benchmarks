use crate::io;

/// A wrapper around an `io::Read` that tracks line and column position.
pub struct LineColIterator<R> {
    iter: R,
    /// Current line (1-based).
    line: usize,
    /// Current column (0-based internally; reported as 1-based).
    col: usize,
    /// Column at the start of the current line.
    start_of_line: usize,
}

impl<R: io::Read> LineColIterator<R> {
    /// Creates a new `LineColIterator` wrapping the given reader.
    pub fn new(iter: R) -> Self {
        LineColIterator {
            iter,
            line: 1,
            col: 0,
            start_of_line: 0,
        }
    }

    /// Returns the current line number (1-based).
    pub fn line(&self) -> usize {
        self.line
    }

    /// Returns the current column number (1-based).
    pub fn col(&self) -> usize {
        self.col
    }
}

impl<R: io::Read> Iterator for LineColIterator<R> {
    type Item = io::Result<u8>;

    fn next(&mut self) -> Option<io::Result<u8>> {
        let mut buf = [0u8; 1];
        match self.iter.read(&mut buf) {
            Ok(0) => None,
            Ok(_) => {
                let byte = buf[0];
                if byte == b'\n' {
                    self.line += 1;
                    self.col = 0;
                } else {
                    self.col += 1;
                }
                Some(Ok(byte))
            }
            Err(e) => Some(Err(e)),
        }
    }
}
