# Cross-platform font fixtures

Unmodified DejaVu Sans Bold (TrueType) from the Linux engine image's
`fonts-dejavu-core` package, and Source Sans 3 Bold (CFF/OpenType) from Adobe's
[release branch](https://github.com/adobe-fonts/source-sans/tree/release/OTF).
Their accompanying Bitstream Vera and SIL Open Font License notices are included.

The verification suite uploads these files into an isolated Studio data store;
it does not install them into the operating system. Both platforms use the same
font bytes. `STUDIO_TEST_TTF` and `STUDIO_TEST_OTF` can override the fixture paths.
