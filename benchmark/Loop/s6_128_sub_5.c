/*
Copyright (c) 2019, Ameer Haj Ali (UC Berkeley), and Intel Corporation
All rights reserved.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/
#include "header.h"

int sum[128] ALIGNED16;
int in1[128] ALIGNED16;
int in2[128] ALIGNED16;

__attribute__((noinline))
void example4b () {
   int i;

   /* feature: support for read accesses with a compile time known misalignment  */
//#pragma clang loop vectorize_width(64) interleave_count(16)
//#pragma clang loop vectorize_width(64) interleave_count(16)
   for (i=0; i<128-4; i++){
      sum[i] = in1[i+1] -in2[i+3];
   }
}

int main(int argc,char* argv[]){
  init_memory(&sum[0], &sum[128]);
  init_memory(&in1[0], &in1[128]);
  init_memory(&in2[0], &in2[128]);
 
  BENCH("Example4b",  example4b(), Mi*2/128*512, digest_memory(&sum[0], &sum[128]));
  
  return 0;
}
