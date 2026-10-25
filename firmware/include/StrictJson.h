#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace basu {

// Bounded syntax-only pass: ArduinoJson builds the document afterwards. Its
// permissive key/string handling must not turn malformed serial data into a
// different command. No allocations or second document tree are needed here.
class StrictJson {
 public:
  StrictJson(const char* bytes, std::size_t count) : bytes_(bytes), count_(count) {}
  bool objectFrame() {
    spaces();
    if (!take('{') || !object(1)) return false;
    spaces();
    return position_ == count_;
  }

 private:
  unsigned char current() const {
    return position_ < count_ ? static_cast<unsigned char>(bytes_[position_]) : 0;
  }
  bool take(char expected) {
    if (position_ == count_ || current() != static_cast<unsigned char>(expected)) return false;
    ++position_;
    return true;
  }
  void spaces() {
    while (position_ < count_ && (current() == ' ' || current() == '\t' ||
           current() == '\r' || current() == '\n')) ++position_;
  }
  bool digits() {
    const auto start = position_;
    while (current() >= '0' && current() <= '9') ++position_;
    return position_ != start;
  }
  bool number() {
    take('-');
    if (!take('0')) {
      if (current() < '1' || current() > '9') return false;
      digits();
    }
    if (take('.') && !digits()) return false;
    if (take('e') || take('E')) {
      if (!take('+')) take('-');
      if (!digits()) return false;
    }
    return true;
  }
  bool literal(const char* text) {
    const auto length = std::strlen(text);
    if (length > count_ - position_ || std::memcmp(bytes_ + position_, text, length)) return false;
    position_ += length;
    return true;
  }
  bool hex4(uint16_t& result) {
    result = 0;
    for (int i = 0; i < 4; ++i) {
      const auto ch = current();
      int digit = ch >= '0' && ch <= '9' ? ch - '0' :
                  ch >= 'a' && ch <= 'f' ? ch - 'a' + 10 :
                  ch >= 'A' && ch <= 'F' ? ch - 'A' + 10 : -1;
      if (digit < 0 || position_ == count_) return false;
      result = static_cast<uint16_t>((result << 4) | digit);
      ++position_;
    }
    return true;
  }
  bool unicodeEscape() {
    uint16_t code = 0;
    if (!hex4(code) || code == 0) return false;  // Embedded NUL truncates C string consumers.
    if (code >= 0xdc00 && code <= 0xdfff) return false;
    if (code < 0xd800 || code > 0xdbff) return true;
    uint16_t low = 0;
    return take('\\') && take('u') && hex4(low) && low >= 0xdc00 && low <= 0xdfff;
  }
  bool utf8(unsigned char first) {
    int following;
    uint32_t code;
    uint32_t minimum;
    if (first >= 0xc2 && first <= 0xdf) { following = 1; code = first & 0x1f; minimum = 0x80; }
    else if (first >= 0xe0 && first <= 0xef) { following = 2; code = first & 0x0f; minimum = 0x800; }
    else if (first >= 0xf0 && first <= 0xf4) { following = 3; code = first & 7; minimum = 0x10000; }
    else return false;
    for (int i = 0; i < following; ++i) {
      if (position_ == count_ || (current() & 0xc0) != 0x80) return false;
      code = (code << 6) | (current() & 0x3f);
      ++position_;
    }
    return code >= minimum && code <= 0x10ffff && !(code >= 0xd800 && code <= 0xdfff);
  }
  bool string() {
    if (!take('"')) return false;
    while (position_ < count_) {
      const auto ch = current();
      ++position_;
      if (ch == '"') return true;
      if (ch < 0x20) return false;
      if (ch == '\\') {
        if (position_ == count_) return false;
        const auto escape = current();
        ++position_;
        if (escape == 'u') { if (!unicodeEscape()) return false; }
        else if (escape != '"' && escape != '\\' && escape != '/' && escape != 'b' &&
                 escape != 'f' && escape != 'n' && escape != 'r' && escape != 't') return false;
      } else if (ch >= 0x80 && !utf8(ch)) return false;
    }
    return false;
  }
  bool value(unsigned depth) {
    spaces();
    if (current() == '"') return string();
    if (take('{')) return depth < 8 && object(depth + 1);
    if (take('[')) return depth < 8 && array(depth + 1);
    if (current() == 't') return literal("true");
    if (current() == 'f') return literal("false");
    if (current() == 'n') return literal("null");
    return number();
  }
  bool object(unsigned depth) {
    spaces();
    if (take('}')) return true;
    do {
      spaces();
      if (!string()) return false;
      spaces();
      if (!take(':') || !value(depth)) return false;
      spaces();
      if (take('}')) return true;
    } while (take(','));
    return false;
  }
  bool array(unsigned depth) {
    spaces();
    if (take(']')) return true;
    do {
      if (!value(depth)) return false;
      spaces();
      if (take(']')) return true;
    } while (take(','));
    return false;
  }

  const char* bytes_;
  std::size_t count_;
  std::size_t position_ = 0;
};

}  // namespace basu
