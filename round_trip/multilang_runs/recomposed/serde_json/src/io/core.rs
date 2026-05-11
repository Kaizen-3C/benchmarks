use core::result;

#[derive(Debug)]
pub struct Error;

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum ErrorKind {
    Other,
}

pub type Result<T> = result::Result<T, Error>;

pub trait Write {
    fn write(&mut self, buf: &[u8]) -> Result<usize>;
    fn write_all(&mut self, buf: &[u8]) -> Result<()> {
        let mut remaining = buf;
        while !remaining.is_empty() {
            match self.write(remaining) {
                Ok(0) => return Err(Error),
                Ok(n) => remaining = &remaining[n..],
                Err(e) => return Err(e),
            }
        }
        Ok(())
    }
    fn flush(&mut self) -> Result<()>;
}

impl Write for alloc::vec::Vec<u8> {
    #[inline]
    fn write(&mut self, buf: &[u8]) -> Result<usize> {
        self.extend_from_slice(buf);
        Ok(buf.len())
    }

    #[inline]
    fn write_all(&mut self, buf: &[u8]) -> Result<()> {
        self.extend_from_slice(buf);
        Ok(())
    }

    #[inline]
    fn flush(&mut self) -> Result<()> {
        Ok(())
    }
}

impl<W: Write + ?Sized> Write for &mut W {
    #[inline]
    fn write(&mut self, buf: &[u8]) -> Result<usize> {
        (**self).write(buf)
    }

    #[inline]
    fn write_all(&mut self, buf: &[u8]) -> Result<()> {
        (**self).write_all(buf)
    }

    #[inline]
    fn flush(&mut self) -> Result<()> {
        (**self).flush()
    }
}
