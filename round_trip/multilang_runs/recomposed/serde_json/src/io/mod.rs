#[cfg(feature = "std")]
mod imp {
    pub use std::io::{Bytes, Error, ErrorKind, Read, Result, Write};
}

#[cfg(not(feature = "std"))]
mod imp {
    pub use self::core::*;
    mod core {
        use core::result;

        #[derive(Debug)]
        pub struct Error;

        #[derive(Debug)]
        pub enum ErrorKind {
            Other,
        }

        pub type Result<T> = result::Result<T, Error>;

        pub trait Write {
            fn write(&mut self, buf: &[u8]) -> Result<usize>;
            fn write_all(&mut self, buf: &[u8]) -> Result<()>;
            fn flush(&mut self) -> Result<()>;
        }

        impl Write for alloc::vec::Vec<u8> {
            fn write(&mut self, buf: &[u8]) -> Result<usize> {
                self.extend_from_slice(buf);
                Ok(buf.len())
            }

            fn write_all(&mut self, buf: &[u8]) -> Result<()> {
                self.extend_from_slice(buf);
                Ok(())
            }

            fn flush(&mut self) -> Result<()> {
                Ok(())
            }
        }

        impl<W: Write + ?Sized> Write for &mut W {
            fn write(&mut self, buf: &[u8]) -> Result<usize> {
                (**self).write(buf)
            }

            fn write_all(&mut self, buf: &[u8]) -> Result<()> {
                (**self).write_all(buf)
            }

            fn flush(&mut self) -> Result<()> {
                (**self).flush()
            }
        }
    }
}

pub use self::imp::*;
